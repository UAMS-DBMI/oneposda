"""Database access for the ingest pipeline.

Deliberately thin. The Perl workers run every statement under DBI's default
AutoCommit, with no explicit transactions, so a file that fails partway
through leaves the rows it already wrote. That is reproduced here: the port
is being verified by exact row diff against the Perl, and wrapping each file
in a transaction would change what lands in the database after an error.

Connection parameters come from the standard libpq environment
(``PGHOST``/``PGUSER``/``PGPASSWORD``), which is how the containers are
configured and how ``Posda::Config::Database`` ends up connecting -- the
``Config/databases.json`` entries carry only a database name and driver.
"""

from __future__ import annotations

import os
from typing import Any, Iterator, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor


class Database:
    """A single autocommit connection, with fetch helpers shaped like DBI's."""

    def __init__(self, dbname: str = "posda_files", **overrides: Any) -> None:
        # POSDA_INGEST_DB redirects the whole pipeline at a scratch database.
        # The Perl RT bridge honours the same variable, so both halves of a
        # differential run land in the same place.
        dbname = os.environ.get("POSDA_INGEST_DB", dbname)
        self.dbname = dbname
        params: dict[str, Any] = {"dbname": dbname}
        # Allow tests and the verification harness to point at a scratch
        # database without disturbing the container's libpq environment.
        for key in ("host", "port", "user", "password"):
            env = os.environ.get(f"POSDA_INGEST_PG{key.upper()}")
            if env is not None:
                params[key] = env
        params.update(overrides)
        self.connection = psycopg2.connect(**params)
        self.connection.autocommit = True

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self.connection.cursor() as cur:
            cur.execute(sql, params)

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        """Equivalent of ``$sth->execute(...); $sth->fetchrow_hashref()``."""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def fetchall(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Iterator[dict[str, Any]]:
        with self.connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            for row in cur:
                yield dict(row)

    def insert_returning(self, sql: str, params: Sequence[Any], column: str) -> Any:
        """Insert and return a generated key.

        The Perl does ``insert`` followed by ``select currval('..._seq')``.
        ``currval`` is session-scoped, so ``RETURNING`` yields the same value
        while removing the second round trip.
        """
        with self.connection.cursor() as cur:
            cur.execute(f"{sql} returning {column}", params)
            row = cur.fetchone()
            return row[0] if row is not None else None

    def ping(self) -> bool:
        try:
            with self.connection.cursor() as cur:
                cur.execute("select 1")
            return True
        except psycopg2.Error:
            return False
