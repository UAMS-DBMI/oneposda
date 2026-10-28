"""The Redis side of the work queue: producers LPUSH work ids, we BRPOP them."""

from __future__ import annotations

import logging

import redis

log = logging.getLogger(__name__)

#: Must exceed the brpop block time, or every empty poll times out at the
#: socket layer (redis-py >= 8 defaults socket_timeout to 5s).
SOCKET_TIMEOUT = 10


def connect(host: str) -> redis.StrictRedis:
    return redis.StrictRedis(
        host=host, db=0, decode_responses=True, socket_timeout=SOCKET_TIMEOUT
    )


def pop_work_id(
    redis_db: redis.StrictRedis, queue_name: str, timeout: int = 5
) -> str | None:
    """Block up to ``timeout`` seconds for the next work id; None on timeout.

    Popping is the claim: BRPOP hands each id to exactly one consumer.
    """
    log.debug("BRBPOP from %s", queue_name)
    result = redis_db.brpop(keys=queue_name, timeout=timeout)
    log.debug(result)
    if result is None:
        return None
    _, work_id = result
    return work_id


def push_work_id(redis_db: redis.StrictRedis, queue_name: str, work_id: int) -> None:
    """Queue one work id for whichever worker pops ``queue_name`` next."""
    log.debug("LPUSH %s onto %s", work_id, queue_name)
    redis_db.lpush(queue_name, work_id)
