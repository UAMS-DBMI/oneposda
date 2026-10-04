"""The Redis queue shared by the ingest daemon and its workers.

The payload format is deliberately byte-identical to the Perl's so that
Python and Perl workers can run against the same queue at the same time,
which is what makes a gradual cutover possible:

- ``files`` -- list of ``[file_id, path]`` JSON arrays, pushed with LPUSH by
  the daemon and popped with BRPOP by the file workers.
- ``pixel_location`` -- the same payloads, forwarded with RPUSH by a file
  worker once it has finished, consumed by the pixel workers.

Shutdown is *not* part of the protocol. The Perl signals it through a
``quit`` key that every process polls, which makes stopping one process stop
all of them; the Python side handles SIGTERM per process instead. See
``posda.ingest.lifecycle``. A Perl worker left running alongside these will
therefore no longer be stopped by the Python daemon.
"""

from __future__ import annotations

import logging
import os

import redis

log = logging.getLogger(__name__)

FILE_QUEUE = "files"
PIXEL_QUEUE = "pixel_location"

DEFAULT_PORT = 6379

# How long the workers ask BRPOP to block for.
POP_TIMEOUT = 5

# redis-py 8 changed socket_timeout from None to 5s, so a BRPOP that blocks
# for its full POP_TIMEOUT -- i.e. every poll of an empty queue -- loses the
# race with the socket read deadline and raises TimeoutError. The read
# timeout has to stay comfortably above POP_TIMEOUT.
SOCKET_TIMEOUT = POP_TIMEOUT * 2


def connect(host: str | None = None, port: int = DEFAULT_PORT) -> redis.Redis:
    """Connect using POSDA_REDIS_HOST, as Config('redis_host') does."""
    host = host or os.environ.get("POSDA_REDIS_HOST", "redis")
    return redis.Redis(
        host=host,
        port=port,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT,
    )
