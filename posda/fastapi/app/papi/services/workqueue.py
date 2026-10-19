"""Handing work to the background workers: Redis db 0, ``work_queue_<n>``.

Workers BRPOP work ids from the queue named on the ``work`` row
(``posda.worker.workqueue``); the API LPUSHes after the row is committed.
Login tokens live in Redis db 1 (``papi.util.redisqueue``), so this module
keeps its own client.
"""

from typing import Protocol

import asyncpg
import redis

from .settings import get_settings


class WorkQueue(Protocol):
    def lpush(self, name: str, *values: str) -> int: ...


_client: redis.StrictRedis | None = None


def get_work_queue() -> redis.StrictRedis:
    global _client
    if _client is None:
        _client = redis.StrictRedis(
            host=get_settings().redis_host, db=0, decode_responses=True
        )
    return _client


def queue_name(priority: int) -> str:
    return f"work_queue_{priority}"


def push_work(queue: WorkQueue, name: str, work_id: int) -> None:
    queue.lpush(name, str(work_id))


async def pending_work_count(conn: asyncpg.Connection) -> int:
    """Items not yet finished, as GetWorkerQueueLength reported it."""
    return int(
        await conn.fetchval(
            "select count(*) from work where status is distinct from 'finished' "
            "and failed = false"
        )
    )
