"""Shared fixtures for the Posda API tests.

Database tests run against the dev compose database (localhost:5433) inside a
transaction that is rolled back after each test, so they never leave rows
behind. They skip when no server is reachable.
"""

import os
import tempfile
from collections.abc import AsyncIterator

import asyncpg
import pytest

os.environ.setdefault("PGHOST", "localhost")
os.environ.setdefault("PGPORT", "5433")
os.environ.setdefault("PGUSER", "postgres")
os.environ.setdefault("PGPASSWORD", "example")
os.environ.setdefault("PGDATABASE", "posda_files")
# main.py creates this directory at import time; keep it out of /home/posda.
os.environ.setdefault("TEMP_STORAGE_PATH", tempfile.mkdtemp(prefix="posda-api-tests-"))


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    """A connection whose work is rolled back when the test ends."""
    try:
        connection = await asyncpg.connect()
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"dev database not reachable: {exc}")
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()
