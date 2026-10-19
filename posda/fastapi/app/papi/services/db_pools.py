"""Connection pools for the databases that saved queries run against.

Saved queries name a database alias in their ``schema`` column, and the alias
is resolved through the same ``databases.json`` the Perl code reads via
``Posda::Config::Database``. Postgres aliases carry only a database name (host,
port and credentials come from the ``PG*`` environment, as for the main pool);
MySQL aliases carry host and credentials explicitly.

Pools are created lazily, one per alias per process, and stay small: a query
run holds one connection for its whole life, so ``max_size`` bounds how many
runs a process can serve at once.
"""

import asyncio
import inspect
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import asyncpg

from .queries.codecs import install_text_codecs
from .settings import get_settings

Driver = Literal["postgres", "mysql"]

POOL_MAX_SIZE = 3
MYSQL_DEFAULT_PORT = 3306


class DatabaseConfigError(ValueError):
    """databases.json is missing, unreadable, or names an unusable alias."""


class UnknownDatabaseAlias(LookupError):
    """A saved query's schema is not an alias in databases.json."""


@dataclass(frozen=True)
class DatabaseAlias:
    name: str
    driver: Driver
    database: str
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None


def _parse_alias(name: str, raw: dict[str, Any]) -> DatabaseAlias:
    driver = raw.get("driver")
    if driver not in ("postgres", "mysql"):
        raise DatabaseConfigError(f"alias {name!r} has unsupported driver {driver!r}")
    database = raw.get("database")
    if not isinstance(database, str) or not database:
        raise DatabaseConfigError(f"alias {name!r} has no database name")
    port = raw.get("port")
    return DatabaseAlias(
        name=name,
        driver=driver,
        database=database,
        host=raw.get("host"),
        port=int(port) if port is not None else None,
        user=raw.get("user"),
        password=raw.get("password"),
    )


def load_database_config(path: Path) -> dict[str, DatabaseAlias]:
    """Parse databases.json into aliases, rejecting anything malformed."""
    try:
        raw = json.loads(path.read_text())
    except OSError as exc:
        raise DatabaseConfigError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DatabaseConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise DatabaseConfigError(f"{path} must hold an object of aliases")
    return {name: _parse_alias(name, entry) for name, entry in raw.items()}


class PoolRegistry:
    """Lazily created pools keyed by databases.json alias."""

    def __init__(
        self, aliases: dict[str, DatabaseAlias], *, max_size: int = POOL_MAX_SIZE
    ) -> None:
        self._aliases = aliases
        self._max_size = max_size
        self._pools: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def alias(self, name: str) -> DatabaseAlias:
        try:
            return self._aliases[name]
        except KeyError:
            raise UnknownDatabaseAlias(name) from None

    def has(self, name: str) -> bool:
        return name in self._aliases

    def unavailable_reason(self, name: str) -> str | None:
        """Why a query against this alias cannot run, or None if it can."""
        if name not in self._aliases:
            return f"schema {name!r} is not configured in databases.json"
        if self._aliases[name].driver == "mysql" and not _mysql_driver_present():
            return "aiomysql is not installed in the API image"
        return None

    async def _pool(self, name: str) -> Any:
        if name in self._pools:
            return self._pools[name]
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            if name not in self._pools:
                self._pools[name] = await self._create_pool(self.alias(name))
        return self._pools[name]

    async def _create_pool(self, alias: DatabaseAlias) -> Any:
        if alias.driver == "postgres":
            return await asyncpg.create_pool(
                database=alias.database,
                host=alias.host,
                port=alias.port,
                user=alias.user,
                password=alias.password,
                min_size=0,
                max_size=self._max_size,
                init=install_text_codecs,
            )
        import aiomysql  # optional dependency; see unavailable_reason()

        return await aiomysql.create_pool(
            host=alias.host or "localhost",
            port=alias.port or MYSQL_DEFAULT_PORT,
            user=alias.user,
            password=alias.password or "",
            db=alias.database,
            minsize=0,
            maxsize=self._max_size,
            autocommit=True,
        )

    @asynccontextmanager
    async def connection(self, name: str) -> AsyncIterator[Any]:
        """A pooled connection for the alias; asyncpg or aiomysql by driver."""
        pool = await self._pool(name)
        async with pool.acquire() as conn:
            yield conn

    async def close(self) -> None:
        pools, self._pools = self._pools, {}
        for pool in pools.values():
            # asyncpg's close() is a coroutine; aiomysql's is sync + wait_closed().
            closing = pool.close()
            if inspect.isawaitable(closing):
                await closing
            else:
                await pool.wait_closed()


def _mysql_driver_present() -> bool:
    try:
        import aiomysql  # noqa: F401
    except ImportError:
        return False
    return True


_registry: PoolRegistry | None = None


def get_pools() -> PoolRegistry:
    """The process-wide registry, built from POSDA_DATABASE_CONFIG on first use."""
    global _registry
    if _registry is None:
        _registry = PoolRegistry(load_database_config(get_settings().database_config))
    return _registry
