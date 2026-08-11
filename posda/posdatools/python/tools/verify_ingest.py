#!/usr/bin/env python3
"""Differential verification of the Python ingest port against the Perl.

Runs both implementations over the same corpus into two throwaway copies of
the posda_files schema, then diffs every table row by row.

The Perl side runs the *unmodified* FastFileProcessWorker.pl and
FastPixelInfoWorker.pl. Nothing is transcribed or reimplemented for the
comparison: the scratch database is substituted underneath them by pointing
POSDA_DATABASE_CONFIG at a generated databases.json whose `posda_files` entry
names the scratch database. The `posda_queries` entry is left pointing at the
real posda_files so query definitions still resolve, while the queries
themselves execute against the scratch copy.

Both sides run strictly single-threaded, and that is not optional. The shared
lookup tables (window_level, slope_intercept, unique_pixel_data) use
check-then-insert with no unique constraint, so the production five-worker
configuration races and produces a nondeterministic number of duplicate rows.
Verified in the dev database: 3 of 4 slope_intercept rows were duplicates.
Diffing that against anything would be meaningless.

Usage:
    verify_ingest.py --corpus DIR [--keep] [--posda-container NAME]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BRIDGE_SCRIPT = "PosdaIngestRtBridge.pl"

PERL_DB = "posda_verify_perl"
PYTHON_DB = "posda_verify_python"
SOURCE_DB = "posda_files"

# Tables that record the run itself rather than the parse, and would differ
# between two runs for uninteresting reasons.
IGNORED_TABLES = {"query_log", "activity_timepoint", "import_event"}


@dataclass
class Config:
    posda_container: str
    db_container: str
    corpus: Path
    storage_root: str = "/tmp/verify_corpus"
    keep: bool = False


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def psql(cfg: Config, database: str, sql: str, quiet: bool = True):
    args = [
        "docker",
        "exec",
        "-i",
        cfg.db_container,
        "psql",
        "-U",
        "postgres",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
    ]
    if quiet:
        args += ["-tAq"]
    result = run(args + ["-c", sql])
    if result.returncode != 0:
        raise RuntimeError(f"psql failed on {database}: {result.stderr.strip()}")
    return result.stdout


def in_posda(cfg: Config, script: str, env: dict[str, str] | None = None) -> str:
    """Run a shell snippet inside the posda container with SetEnv sourced."""
    exports = ""
    if env:
        exports = "".join(f"export {k}={v}; " for k, v in env.items())
    command = (
        "cd /home/posda/posdatools && shopt -s globstar && "
        "source Config/SetEnv >/dev/null 2>&1; " + exports + script
    )
    result = run(["docker", "exec", cfg.posda_container, "bash", "-lc", command])
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed in {cfg.posda_container}: {result.stderr.strip()}"
        )
    return result.stdout


# --------------------------------------------------------------------------
# setup


def create_databases(cfg: Config) -> None:
    for database in (PERL_DB, PYTHON_DB):
        psql(cfg, "postgres", f'drop database if exists "{database}"')
        psql(cfg, "postgres", f'create database "{database}"')
        dump = (
            f"pg_dump -U postgres --schema-only {SOURCE_DB} "
            f"| psql -U postgres -q -d {database}"
        )
        result = run(["docker", "exec", cfg.db_container, "bash", "-c", dump])
        if result.returncode != 0:
            raise RuntimeError(f"schema copy failed: {result.stderr.strip()}")
        print(f"  created {database}")


def seed_corpus(cfg: Config, files: list[Path]) -> None:
    """Insert identical file/file_location rows into both databases."""
    values = []
    locations = []
    for index, path in enumerate(files, start=1):
        digest = path.name  # a stand-in; the parse recomputes the real one
        values.append(f"({index}, '{digest}', {path.stat().st_size}, null, true, 1)")
        locations.append(f"({index}, 1, '{path.name}', false)")

    for database in (PERL_DB, PYTHON_DB):
        psql(cfg, database, "delete from file_location; delete from file;")
        psql(
            cfg,
            database,
            "insert into file_storage_root"
            " (file_storage_root_id, root_path, current, storage_class)"
            f" values (1, '{cfg.storage_root}', true, 'verify')"
            " on conflict do nothing",
        )
        psql(
            cfg,
            database,
            "insert into file (file_id, digest, size, is_dicom_file,"
            " ready_to_process, processing_priority) values " + ", ".join(values),
        )
        psql(
            cfg,
            database,
            "insert into file_location (file_id, file_storage_root_id,"
            " rel_path, file_is_present) values " + ", ".join(locations),
        )
    print(f"  seeded {len(files)} files into both databases")


def stage_corpus(cfg: Config, files: list[Path]) -> None:
    """Copy the corpus into the posda container at the storage root."""
    in_posda(cfg, f"rm -rf {cfg.storage_root}; mkdir -p {cfg.storage_root}")
    for path in files:
        result = run(
            [
                "docker",
                "cp",
                str(path),
                f"{cfg.posda_container}:{cfg.storage_root}/{path.name}",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"could not stage {path}: {result.stderr.strip()}")
    print(f"  staged {len(files)} files at {cfg.storage_root}")


def write_database_config(cfg: Config) -> str:
    """Generate a databases.json whose posda_files entry is the scratch DB."""
    raw = in_posda(cfg, "cat Config/databases.json")
    stripped = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("//")
    )
    config = json.loads(stripped)
    config["posda_files"] = dict(config["posda_files"], database=PERL_DB)
    # Leave posda_queries pointing at the real database so query definitions
    # still resolve; they will execute against the scratch copy because their
    # schema column says posda_files.
    path = "/tmp/verify_databases.json"
    encoded = json.dumps(config).replace("'", "'\\''")
    in_posda(cfg, f"cat > {path} <<'JSONEOF'\n{encoded}\nJSONEOF")
    return path


# --------------------------------------------------------------------------
# runs


def start_verify_redis(cfg: Config) -> str:
    """A private Redis so the stock workers cannot touch the live queues.

    The Perl workers hardcode Redis logical database 0, so isolation has to
    come from a separate server rather than a separate database number.
    """
    name = "posda-verify-redis"
    network = run(
        [
            "docker",
            "inspect",
            cfg.posda_container,
            "--format",
            "{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}",
        ]
    ).stdout.strip()
    run(["docker", "rm", "-f", name])
    result = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "redis:8-alpine",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not start verify redis: {result.stderr.strip()}")
    return name


def _wait_for(
    cfg: Config,
    redis_host: str,
    expression: str,
    target: int,
    label: str,
    timeout: int = 900,
) -> None:
    """Poll a redis LLEN until it reaches the target."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        value = in_posda(cfg, f"redis-cli -h {redis_host} {expression}").strip()
        if value.isdigit() and int(value) == target:
            return
        time.sleep(1)
    raise TimeoutError(f"timed out waiting for {label}")


def run_perl(cfg: Config, files: list[Path], database_config: str) -> None:
    """Drive the unmodified Perl workers against the scratch database."""
    redis_host = start_verify_redis(cfg)
    env = {
        "POSDA_DATABASE_CONFIG": database_config,
        "POSDA_REDIS_HOST": redis_host,
    }
    payloads = [
        json.dumps([index, f"{cfg.storage_root}/{path.name}"], separators=(",", ":"))
        for index, path in enumerate(files, start=1)
    ]
    # LPUSH, matching the daemon: the workers BRPOP from the tail, so
    # pushing to the head is what makes the queue FIFO. Using RPUSH here
    # reverses the processing order, which shifts every generated surrogate
    # key and makes the diff unreadable.
    push = "; ".join(
        f"redis-cli -h {redis_host} lpush files '{payload}' >/dev/null"
        for payload in payloads
    )
    in_posda(cfg, f"redis-cli -h {redis_host} flushall >/dev/null; {push}")
    print(f"  queued {len(payloads)} items on {redis_host}")

    # One worker only: the shared lookup tables race under concurrency.
    _run_detached(cfg, "Posda/bin/FastFileProcessWorker.pl", env, "ffpw.log")
    _wait_for(cfg, redis_host, "llen pixel_location", len(files), "file worker")
    print(f"  file worker processed {len(files)} files")

    _run_detached(cfg, "Posda/bin/FastPixelInfoWorker.pl", env, "fpiw.log")
    _wait_for(cfg, redis_host, "llen pixel_location", 0, "pixel worker")
    print("  pixel worker drained the queue")

    in_posda(cfg, f"redis-cli -h {redis_host} set quit 1 >/dev/null")
    import time

    time.sleep(8)  # let both loops notice the quit key and exit cleanly
    run(["docker", "rm", "-f", redis_host])


def _run_detached(cfg: Config, script: str, env: dict[str, str], log: str) -> None:
    exports = "".join(f"export {k}={v}; " for k, v in env.items())
    command = (
        "cd /home/posda/posdatools && shopt -s globstar && "
        "source Config/SetEnv >/dev/null 2>&1; "
        + exports
        + f"nohup {script} > /tmp/{log} 2>&1 &"
    )
    run(["docker", "exec", "-d", cfg.posda_container, "bash", "-lc", command])


PYTHON_DRIVER = """
import sys
sys.path.insert(0, {stage!r})
from posda.ingest.db import Database
from posda.ingest import pixel_worker, worker
from posda.ingest.worker import FileJob

files = {files!r}
root = {root!r}
db = Database()
for index, name in enumerate(files, start=1):
    job = FileJob(index, f"{{root}}/{{name}}")
    worker.process_file(db, job)
    pixel_worker.populate_pixel_info(db, job)
print(f"processed {{len(files)}} files")
"""


def run_python(cfg: Config, files: list[Path]) -> None:
    """Run the Python pipeline in the same container, single-threaded."""
    # A fresh staging directory each run: docker cp writes as root while the
    # container's shell is the posda user, so a reused path cannot be cleaned.
    import os
    import time

    stage = f"/tmp/pyingest-{int(time.time())}-{os.getpid()}"
    package = Path(__file__).resolve().parents[1] / "posda" / "ingest"
    in_posda(cfg, f"mkdir -p {stage}/posda")
    result = run(
        ["docker", "cp", str(package), f"{cfg.posda_container}:{stage}/posda/"]
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not stage package: {result.stderr.strip()}")
    in_posda(cfg, f"touch {stage}/posda/__init__.py")

    # The RT bridge lives in Posda/bin, which belongs to the mounted tree
    # rather than this checkout, so stage it alongside the package.
    bridge = Path(__file__).resolve().parents[2] / "Posda" / "bin" / BRIDGE_SCRIPT
    result = run(["docker", "cp", str(bridge), f"{cfg.posda_container}:{stage}/"])
    if result.returncode != 0:
        raise RuntimeError(f"could not stage rt bridge: {result.stderr.strip()}")

    driver = PYTHON_DRIVER.format(
        files=[p.name for p in files], root=cfg.storage_root, stage=stage
    )
    in_posda(cfg, f"cat > {stage}/driver.py <<'PYEOF'\n{driver}\nPYEOF")
    out = in_posda(
        cfg,
        f"python3 {stage}/driver.py",
        env={
            "POSDA_INGEST_DB": PYTHON_DB,
            "POSDA_RT_BRIDGE": f"{stage}/{BRIDGE_SCRIPT}",
        },
    )
    print("  " + out.strip().splitlines()[-1])


# --------------------------------------------------------------------------
# diff


def table_columns(cfg: Config, database: str, table: str) -> list[str]:
    out = psql(
        cfg,
        database,
        "select column_name from information_schema.columns"
        f" where table_schema='public' and table_name='{table}'"
        " order by ordinal_position",
    )
    return [line for line in out.splitlines() if line]


def dump_table(cfg: Config, database: str, table: str, columns: list[str]) -> str:
    column_list = ", ".join(f'"{c}"' for c in columns)
    return psql(
        cfg,
        database,
        f"select {column_list} from {table} order by {column_list}",
    )


def diff_tables(cfg: Config) -> int:
    perl_counts = exact_counts(cfg, PERL_DB)
    python_counts = exact_counts(cfg, PYTHON_DB)

    tables = sorted(set(perl_counts) | set(python_counts))
    mismatches = 0
    compared = 0

    print(f"\n{'table':<34} {'perl':>7} {'python':>7}  result")
    print("-" * 66)
    for table in tables:
        if table in IGNORED_TABLES:
            continue
        perl_n = perl_counts.get(table, 0)
        python_n = python_counts.get(table, 0)
        if perl_n == 0 and python_n == 0:
            continue
        compared += 1

        if perl_n != python_n:
            print(f"{table:<34} {perl_n:>7} {python_n:>7}  ROW COUNT DIFFERS")
            mismatches += 1
            continue

        columns = table_columns(cfg, PERL_DB, table)
        perl_rows = dump_table(cfg, PERL_DB, table, columns)
        python_rows = dump_table(cfg, PYTHON_DB, table, columns)
        if perl_rows == python_rows:
            print(f"{table:<34} {perl_n:>7} {python_n:>7}  ok")
        else:
            print(f"{table:<34} {perl_n:>7} {python_n:>7}  CONTENT DIFFERS")
            _show_row_diff(perl_rows, python_rows, columns)
            mismatches += 1

    print("-" * 66)
    print(f"{compared} populated tables compared, {mismatches} with differences")
    return mismatches


def exact_counts(cfg: Config, database: str) -> dict[str, int]:
    """Exact row counts for every public table (pg_stat is only an estimate)."""
    out = psql(
        cfg,
        database,
        """
        select string_agg(
          format('select %L as t, count(*) as n from %I', tablename, tablename),
          ' union all ')
        from pg_tables where schemaname='public'
        """,
    ).strip()
    if not out:
        return {}
    rows = psql(cfg, database, out)
    counts = {}
    for line in rows.splitlines():
        if not line:
            continue
        name, count = line.rsplit("|", 1)
        if int(count):
            counts[name] = int(count)
    return counts


def _show_row_diff(perl_rows: str, python_rows: str, columns: list[str]) -> None:
    perl_lines = perl_rows.splitlines()
    python_lines = python_rows.splitlines()
    only_perl = [l for l in perl_lines if l not in python_lines]
    only_python = [l for l in python_lines if l not in perl_lines]
    print(f"      columns: {', '.join(columns)}")
    for line in only_perl[:3]:
        print(f"      perl  only: {line}")
    for line in only_python[:3]:
        print(f"      py    only: {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument(
        "--posda-container", default="oneposda-1661-posda-fast-file-process-1"
    )
    parser.add_argument("--db-container", default="oneposda-1661-db-1")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--diff-only", action="store_true")
    args = parser.parse_args(argv)

    cfg = Config(
        posda_container=args.posda_container,
        db_container=args.db_container,
        corpus=args.corpus,
        keep=args.keep,
    )

    files = sorted(p for p in cfg.corpus.iterdir() if p.is_file())
    if not files:
        print(f"no files in {cfg.corpus}", file=sys.stderr)
        return 2

    if not args.diff_only:
        print("setting up:")
        create_databases(cfg)
        stage_corpus(cfg, files)
        seed_corpus(cfg, files)
        database_config = write_database_config(cfg)
        print("\nrunning perl:")
        run_perl(cfg, files, database_config)
        print("\nrunning python:")
        run_python(cfg, files)

    return 1 if diff_tables(cfg) else 0


if __name__ == "__main__":
    raise SystemExit(main())
