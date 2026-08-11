import asyncpg
import asyncio
import sys

async def run() -> None:
    try:
        conn = await asyncpg.connect(database='posda_files')
        await conn.close()
    except Exception as e:
        print(f"Database check failed: {e}", file=sys.stderr)
        sys.exit(1)

asyncio.run(run())
