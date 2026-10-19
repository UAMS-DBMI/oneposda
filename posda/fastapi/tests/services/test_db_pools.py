import json
from pathlib import Path

import pytest

from papi.services.db_pools import (
    DatabaseConfigError,
    PoolRegistry,
    UnknownDatabaseAlias,
    load_database_config,
)


def write_config(tmp_path: Path, body: object) -> Path:
    path = tmp_path / "databases.json"
    path.write_text(json.dumps(body))
    return path


def test_load_database_config_parses_both_drivers(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "posda_files": {"database": "posda_files", "driver": "postgres"},
            "public": {
                "database": "nbiadb",
                "driver": "mysql",
                "host": "db.example",
                "user": "u",
                "password": "p",
            },
        },
    )
    aliases = load_database_config(path)
    assert aliases["posda_files"].driver == "postgres"
    assert aliases["posda_files"].host is None
    assert aliases["public"].driver == "mysql"
    assert aliases["public"].host == "db.example"


def test_load_database_config_rejects_bad_driver(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"x": {"database": "d", "driver": "oracle"}})
    with pytest.raises(DatabaseConfigError, match="unsupported driver"):
        load_database_config(path)


def test_load_database_config_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DatabaseConfigError, match="cannot read"):
        load_database_config(tmp_path / "nope.json")


def test_registry_explains_unknown_alias(tmp_path: Path) -> None:
    registry = PoolRegistry(load_database_config(write_config(tmp_path, {})))
    assert registry.unavailable_reason("intake") is not None
    with pytest.raises(UnknownDatabaseAlias):
        registry.alias("intake")


async def test_registry_connects_postgres_alias_from_pg_env(
    tmp_path: Path, conn
) -> None:
    path = write_config(
        tmp_path, {"posda_files": {"database": "posda_files", "driver": "postgres"}}
    )
    registry = PoolRegistry(load_database_config(path), max_size=1)
    try:
        async with registry.connection("posda_files") as pooled:
            assert await pooled.fetchval("select 1") == 1
        assert registry.unavailable_reason("posda_files") is None
    finally:
        await registry.close()
