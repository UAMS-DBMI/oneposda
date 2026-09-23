import asyncpg
from contextlib import asynccontextmanager

pool = None
database = 'posda_files'

class NotFound(RuntimeError): pass

class Database:
    def __init__(self):
        pass

    async def execute(self, query, parameters=None):
        global pool
        parameters = parameters or []

        async with pool.acquire() as conn:
            return await conn.execute(query, *parameters)

    async def fetch(self, query, parameters=None):
        global pool
        parameters = parameters or []

        async with pool.acquire() as conn:
            records = await conn.fetch(query, *parameters)
            return records

    async def fetch_one(self, query, parameters=None):
        """Execute query and return the first result, or [] if none match."""
        global pool
        parameters = parameters or []

        async with pool.acquire() as conn:
            records = await conn.fetch(query, *parameters)
            if len(records) < 1:
                return []
            return records[0]

    @asynccontextmanager
    async def transaction(self):
        global pool

        async with pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    def get_pool(self):
        global pool
        return pool


async def setup(*args, **kwargs):
    global pool
    pool = await asyncpg.create_pool(*args, **kwargs)
