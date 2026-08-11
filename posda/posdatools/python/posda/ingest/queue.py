"""The Redis queue shared by the ingest daemon and its workers.

The protocol is deliberately byte-identical to the Perl's so that Python and
Perl workers can run against the same queue at the same time, which is what
makes a gradual cutover possible:

- ``files`` -- list of ``[file_id, path]`` JSON arrays, pushed with LPUSH by
  the daemon and popped with BRPOP by the file workers.
- ``pixel_location`` -- the same payloads, forwarded with RPUSH by a file
  worker once it has finished, consumed by the pixel workers.
- ``quit`` -- when this key exists, every process shuts down.
"""

from __future__ import annotations

import logging
import os

import redis

log = logging.getLogger(__name__)

FILE_QUEUE = "files"
PIXEL_QUEUE = "pixel_location"
QUIT_KEY = "quit"

DEFAULT_PORT = 6379


def connect(host: str | None = None, port: int = DEFAULT_PORT) -> redis.Redis:
    """Connect using POSDA_REDIS_HOST, as Config('redis_host') does."""
    host = host or os.environ.get("POSDA_REDIS_HOST", "redis")
    return redis.Redis(host=host, port=port, decode_responses=True)


def should_quit(client: redis.Redis) -> bool:
    return client.get(QUIT_KEY) is not None


def request_shutdown(client: redis.Redis) -> None:
    client.set(QUIT_KEY, 1)


def clear_shutdown(client: redis.Redis) -> None:
    client.delete(QUIT_KEY)
