"""The original worker loop: BRPOP a work id from Redis, run it, repeat.

This is what ``WorkerNode.py`` with no arguments does, and it must keep
behaving exactly as it did before the code was split into a package: same
environment variables, same queue, same version check, same error handling.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

import redis

from posda.worker import execute, workqueue
from posda.worker.api import PosdaApi
from posda.worker.settings import load_worker_settings

log = logging.getLogger(__name__)

VERSION = 3  # the version of this code, increment only


class SigTerm(SystemExit):
    """SIGTERM converted into an exception so ``finally`` blocks run."""


def _term_handler(signum: int, frame: FrameType | None) -> None:
    raise SigTerm(1)


def install_sigterm_handler() -> None:
    signal.signal(signal.SIGTERM, _term_handler)


def run_legacy() -> None:
    install_sigterm_handler()
    log.info("worker node started")

    settings = load_worker_settings()
    api = PosdaApi(settings.base_url, settings.api_token)

    log.info(
        "configuration loaded: %s",
        {
            "api_url": settings.api_url,
            "redis_host": settings.redis_host,
            "worker_priority": settings.worker_priority,
            "NODE_NAME": settings.node_name,
        },
    )

    redis_db = workqueue.connect(settings.redis_host)
    log.info("connected to redis")

    work_loop(redis_db, settings.queue_name, api, settings.node_name)


def work_loop(
    redis_db: redis.StrictRedis, queue_name: str, api: PosdaApi, node_name: str
) -> None:
    """Continually wait for new work items, and process them."""
    while True:
        restart_if_needed(redis_db)
        work_id = workqueue.pop_work_id(redis_db, queue_name, timeout=5)
        if work_id is None:
            # if the timeout is reached, work_id will be None
            continue

        try:
            execute.process_work_item(api, work_id, node_name)
        except Exception as e:
            log.error(e)
            api.set_status_errored(work_id, None, None, None)


def restart_if_needed(redis_db: redis.StrictRedis) -> None:
    """Check to see if we should exit for upgrade.

    This assumes we are being run by some monitor process that will
    automatically restart us upon exit. So, all we need to do is exit if we
    need an upgrade.
    """
    version = redis_db.get("worker-node-version")
    if version is None:
        log.debug(
            "worker-node-version is not set in redis, "
            "can't know if we need to restart for update."
        )
        return

    try:
        int_version = int(version)
    except ValueError:
        log.error("worker-node-version key is not an integer!")
        return

    if int_version > VERSION:
        log.info(
            "Exiting for automatic upgrade. We are version %s but "
            "the latest version is %s.",
            VERSION,
            int_version,
        )
        sys.exit(1)
