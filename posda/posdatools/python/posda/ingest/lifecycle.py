"""Per-process shutdown handling for the ingest daemon and workers.

Every ingest process is its own pod, so shutdown is per-process: SIGTERM
stops the process that received it and nothing else. There is deliberately no
cluster-wide stop signal -- the pipeline used to keep one in Redis under the
key ``quit``, which meant a rolling restart of the daemon also took down every
worker. Scaling a Deployment to zero is how you stop a tier now.

Kubernetes sends SIGTERM and waits ``terminationGracePeriodSeconds`` before
SIGKILL, so a loop that checks the flag between jobs gets to finish the file
it is holding and exit on its own.
"""

from __future__ import annotations

import logging
import signal
import threading

log = logging.getLogger(__name__)


class ShutdownFlag:
    """Set once SIGTERM or SIGINT arrives, so run loops can wind down."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def install(self) -> "ShutdownFlag":
        """Take over SIGINT and SIGTERM. Returns self so callers can chain."""
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, self._request)
        return self

    def _request(self, signum: int, _frame: object) -> None:
        log.info(
            "Received %s, finishing current work and exiting.",
            signal.Signals(signum).name,
        )
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def sleep(self, seconds: float) -> None:
        """Pause, but return as soon as shutdown is requested.

        Waiting on the event rather than calling ``time.sleep`` keeps the
        idle daemon from sitting out its full poll interval before noticing
        SIGTERM, which is what would otherwise push a quiet pod up against
        the grace period.
        """
        self._event.wait(timeout=seconds)
