"""Tests for the migration runner.

The pure logic (ordering, drift classification, target discovery) is tested
directly. The tests that need a live server are skipped unless one is
reachable, so the suite still runs on a machine without postgres.
"""

import importlib.util
import os
import subprocess
import uuid
from pathlib import Path
from types import ModuleType

import pytest


def load_migrate_module() -> ModuleType:
    """Import the runner, which has no .py suffix and so needs a manual spec."""
    script = Path(__file__).resolve().parent.parent / "migrate"
    spec = importlib.util.spec_from_loader(
        "migrate", importlib.machinery.SourceFileLoader("migrate", str(script))
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrate = load_migrate_module()


def write_migration(directory: Path, name: str, body: str = "select 1;\n") -> Path:
    path = directory / name
    path.write_text(body)
    return path


@pytest.fixture
def target(tmp_path: Path) -> "migrate.Target":
    directory = tmp_path / "posda_test"
    directory.mkdir()
    return migrate.Target(name="posda_test", directory=directory, database="posda_test")


class TestLoadMigrations:
    def test_orders_by_filename_not_directory_order(
        self, target: "migrate.Target"
    ) -> None:
        for name in ["0003_c.sql", "0001_a.sql", "0002_b.sql"]:
            write_migration(target.directory, name)

        names = [m.name for m in migrate.load_migrations(target)]

        assert names == ["0001_a.sql", "0002_b.sql", "0003_c.sql"]

    def test_numeric_legacy_prefixes_sort_before_timestamps(
        self, target: "migrate.Target"
    ) -> None:
        write_migration(target.directory, "20260812_new.sql")
        write_migration(target.directory, "0048_legacy.sql")

        names = [m.name for m in migrate.load_migrations(target)]

        assert names == ["0048_legacy.sql", "20260812_new.sql"]

    def test_excludes_manual_directory(self, target: "migrate.Target") -> None:
        write_migration(target.directory, "0001_a.sql")
        manual = target.directory / "manual"
        manual.mkdir()
        write_migration(manual, "0002_teardown.sql")

        names = [m.name for m in migrate.load_migrations(target)]

        assert names == ["0001_a.sql"]

    def test_includes_shell_migrations_but_not_other_files(
        self, target: "migrate.Target"
    ) -> None:
        write_migration(target.directory, "0001_a.sql")
        write_migration(target.directory, "0002_b.sh", "#!/bin/bash\n")
        write_migration(target.directory, "notes.md", "ignore me\n")

        names = [m.name for m in migrate.load_migrations(target)]

        assert names == ["0001_a.sql", "0002_b.sh"]

    def test_hashes_contents(self, target: "migrate.Target") -> None:
        write_migration(target.directory, "0001_a.sql", "select 1;\n")
        first = migrate.load_migrations(target)[0].sha256

        write_migration(target.directory, "0001_a.sql", "select 2;\n")
        second = migrate.load_migrations(target)[0].sha256

        assert first != second


class TestBuildPlan:
    @staticmethod
    def plan_with(
        monkeypatch: pytest.MonkeyPatch,
        target: "migrate.Target",
        applied: dict[str, str],
    ) -> "migrate.TargetPlan":
        monkeypatch.setattr(migrate, "fetch_applied", lambda _: applied)
        return migrate.build_plan(target)

    def test_unrecorded_file_is_pending(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        write_migration(target.directory, "0001_a.sql")

        plan = self.plan_with(monkeypatch, target, {})

        assert [m.name for m in plan.pending] == ["0001_a.sql"]
        assert plan.applied == []

    def test_recorded_file_with_matching_hash_is_applied(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        path = write_migration(target.directory, "0001_a.sql")
        digest = migrate.sha256_of_file(path)

        plan = self.plan_with(monkeypatch, target, {"0001_a.sql": digest})

        assert plan.pending == []
        assert [m.name for m in plan.applied] == ["0001_a.sql"]
        assert plan.is_clean

    def test_edited_applied_file_is_flagged_as_mismatched(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        write_migration(target.directory, "0001_a.sql")

        plan = self.plan_with(monkeypatch, target, {"0001_a.sql": "stale-hash"})

        assert [m.name for m in plan.mismatched] == ["0001_a.sql"]
        assert plan.pending == []
        assert not plan.is_clean

    def test_ledger_entry_without_a_file_is_flagged_as_missing(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        plan = self.plan_with(monkeypatch, target, {"0001_vanished.sql": "hash"})

        assert plan.missing == ["0001_vanished.sql"]
        assert not plan.is_clean

    def test_migration_merged_behind_the_high_water_mark_is_out_of_order(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        late = write_migration(target.directory, "0002_late.sql")
        write_migration(target.directory, "0001_branch.sql")

        plan = self.plan_with(
            monkeypatch, target, {"0002_late.sql": migrate.sha256_of_file(late)}
        )

        assert [m.name for m in plan.out_of_order] == ["0001_branch.sql"]
        assert not plan.is_clean

    def test_pending_ahead_of_high_water_mark_is_in_order(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        first = write_migration(target.directory, "0001_a.sql")
        write_migration(target.directory, "0002_b.sql")

        plan = self.plan_with(
            monkeypatch, target, {"0001_a.sql": migrate.sha256_of_file(first)}
        )

        assert plan.out_of_order == []
        assert plan.is_clean

    def test_empty_database_never_reports_out_of_order(
        self, monkeypatch: pytest.MonkeyPatch, target: "migrate.Target"
    ) -> None:
        write_migration(target.directory, "0009_z.sql")
        write_migration(target.directory, "0001_a.sql")

        plan = self.plan_with(monkeypatch, target, {})

        assert plan.out_of_order == []


class TestDiscoverTargets:
    def test_finds_each_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / "posda_files").mkdir()
        (tmp_path / "posda_auth").mkdir()

        names = [t.name for t in migrate.discover_targets(tmp_path, [], "")]

        assert names == ["posda_auth", "posda_files"]

    def test_skips_tests_and_hidden_directories(self, tmp_path: Path) -> None:
        (tmp_path / "posda_files").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / ".cache").mkdir()

        names = [t.name for t in migrate.discover_targets(tmp_path, [], "")]

        assert names == ["posda_files"]

    def test_prefix_applies_to_database_not_target_name(self, tmp_path: Path) -> None:
        (tmp_path / "posda_files").mkdir()

        target = migrate.discover_targets(tmp_path, [], "N_")[0]

        assert target.name == "posda_files"
        assert target.database == "N_posda_files"

    def test_unknown_target_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "posda_files").mkdir()

        with pytest.raises(migrate.MigrationError, match="unknown target"):
            migrate.discover_targets(tmp_path, ["nope"], "")


def postgres_is_reachable() -> bool:
    try:
        result = subprocess.run(
            ["psql", "-X", "-c", "select 1", "-d", "postgres"],
            capture_output=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


needs_postgres = pytest.mark.skipif(
    not postgres_is_reachable(),
    reason="no reachable postgres (set PGHOST/PGPORT/PGUSER/PGPASSWORD)",
)


@pytest.fixture
def scratch_database() -> str:
    """A throwaway database, dropped when the test finishes."""
    name = f"migrate_test_{uuid.uuid4().hex[:12]}"
    subprocess.run(
        ["psql", "-X", "-q", "-c", f"create database {name}", "-d", "postgres"],
        check=True,
        capture_output=True,
    )
    try:
        yield name
    finally:
        subprocess.run(
            ["psql", "-X", "-q", "-c", f"drop database {name}", "-d", "postgres"],
            check=True,
            capture_output=True,
        )


@needs_postgres
class TestAgainstRealDatabase:
    @staticmethod
    def make_target(tmp_path: Path, database: str) -> "migrate.Target":
        directory = tmp_path / database
        directory.mkdir()
        return migrate.Target(name=database, directory=directory, database=database)

    def test_ensure_ledger_is_idempotent(
        self, tmp_path: Path, scratch_database: str
    ) -> None:
        target = self.make_target(tmp_path, scratch_database)

        migrate.ensure_ledger(target)
        migrate.ensure_ledger(target)

        assert migrate.fetch_applied(target) == {}

    def test_applying_a_migration_records_it(
        self, tmp_path: Path, scratch_database: str
    ) -> None:
        target = self.make_target(tmp_path, scratch_database)
        write_migration(
            target.directory, "0001_demo.sql", "create table demo (id int);"
        )
        migrate.ensure_ledger(target)

        migration = migrate.load_migrations(target)[0]
        migrate.apply_sql_migration(target, migration)

        assert migrate.fetch_applied(target) == {"0001_demo.sql": migration.sha256}
        assert migrate.build_plan(target).pending == []

    def test_failed_migration_leaves_no_trace(
        self, tmp_path: Path, scratch_database: str
    ) -> None:
        target = self.make_target(tmp_path, scratch_database)
        write_migration(
            target.directory,
            "0001_bad.sql",
            "create table halfway (id int);\nselect 1/0;\n",
        )
        migrate.ensure_ledger(target)
        migration = migrate.load_migrations(target)[0]

        with pytest.raises(migrate.PsqlError):
            migrate.apply_sql_migration(target, migration)

        assert migrate.fetch_applied(target) == {}
        rows = migrate.query_rows(
            scratch_database,
            "select count(*) from information_schema.tables "
            "where table_name = 'halfway'",
        )
        assert rows == [["0"]]

    def test_version_counter_tracks_the_ledger(
        self, tmp_path: Path, scratch_database: str
    ) -> None:
        target = self.make_target(tmp_path, scratch_database)
        write_migration(target.directory, "0001_a.sql", "create table a (id int);")
        write_migration(target.directory, "0002_b.sql", "create table b (id int);")
        migrate.ensure_ledger(target)

        for migration in migrate.load_migrations(target):
            migrate.apply_sql_migration(target, migration)

        rows = migrate.query_rows(
            scratch_database, "select version from db_version.version"
        )
        assert rows == [["2"]]

    def test_filename_containing_a_quote_is_not_injected(
        self, tmp_path: Path, scratch_database: str
    ) -> None:
        target = self.make_target(tmp_path, scratch_database)
        write_migration(target.directory, "0001_o'brien.sql", "select 1;")
        migrate.ensure_ledger(target)

        migration = migrate.load_migrations(target)[0]
        migrate.apply_sql_migration(target, migration)

        assert "0001_o'brien.sql" in migrate.fetch_applied(target)

    def test_baseline_records_without_running(
        self, tmp_path: Path, scratch_database: str
    ) -> None:
        target = self.make_target(tmp_path, scratch_database)
        write_migration(
            target.directory, "0001_would_fail.sql", "this is not valid sql;"
        )
        migrate.ensure_ledger(target)

        migration = migrate.load_migrations(target)[0]
        migrate.record_applied(target, migration)

        assert migrate.build_plan(target).pending == []
