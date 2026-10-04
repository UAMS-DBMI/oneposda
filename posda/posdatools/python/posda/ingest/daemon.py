"""Port of ``FastFileProcessDaemon.pl`` and the worker run loops.

The pipeline runs as three independently scaled tiers, one process per
container:

- ``daemon`` -- refills the Redis ``files`` list from the database whenever
  it drains. Exactly one of these should run; a second would queue the same
  rows twice.
- ``file-worker`` -- parses a file into the database, then forwards it to the
  pixel queue.
- ``pixel-worker`` -- the second pass that records where the pixel data lives.

Nothing here spawns children: under Kubernetes each tier is its own
Deployment and the replica count is the concurrency knob, so a worker process
is a pod and the scheduler decides how many there are. The Perl daemon forked
five of each on startup, which is the behaviour this replaces.

The replenish query and batch size are kept as they are in the Perl -- 1000
rows per refill, a 1s tick, and a 10s pause when the database has nothing to
offer -- but each interval can be tuned per deployment from the environment.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from posda.ingest import pixel_worker, queue, worker
from posda.ingest.db import Database
from posda.ingest.lifecycle import ShutdownFlag
from posda.ingest.worker import FileJob

log = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)


#: Rows per refill. Larger batches mean fewer queries but a longer window in
#: which the daemon cannot notice SIGTERM.
BATCH_SIZE = _env_int("POSDA_INGEST_BATCH_SIZE", 1000)
#: Pause after a refill that found nothing, so an idle pipeline stops
#: hammering the database.
IDLE_SLEEP = _env_int("POSDA_INGEST_IDLE_SLEEP", 10)
#: Delay between queue-depth checks.
TICK = _env_int("POSDA_INGEST_TICK", 1)

REPLENISH_SQL = """
    select file_id, root_path || '/' || rel_path as path
    from file
    natural join file_location
    natural join file_storage_root
    where is_dicom_file is null
      and ready_to_process
      and processing_priority is not null
    limit %s
"""


def replenish(db: Database, client) -> int:
    """Push another batch of pending files onto the queue."""
    count = 0
    for row in db.fetchall(REPLENISH_SQL, [BATCH_SIZE]):
        client.lpush(
            queue.FILE_QUEUE,
            FileJob(file_id=row["file_id"], path=row["path"]).to_json(),
        )
        count += 1
    return count


def run_daemon() -> None:
    shutdown = ShutdownFlag().install()
    db = Database("posda_files")
    client = queue.connect()

    log.info("FFPD: FastFileProcessDaemon starting up...")

    while not shutdown.requested:
        if not db.ping():
            raise RuntimeError("Lost connection to database")

        if client.llen(queue.FILE_QUEUE) == 0:
            count = replenish(db, client)
            if count:
                log.info("FFPD: Added %d files to the queue.", count)
            else:
                shutdown.sleep(IDLE_SLEEP)

        shutdown.sleep(TICK)

    log.info("FFPD: Shut down completed. Goodbye!")
    db.close()


def run_file_worker() -> None:
    """Port of the FastFileProcessWorker.pl main loop."""
    shutdown = ShutdownFlag().install()
    db = Database("posda_files")
    client = queue.connect()
    log.info("FFPW: FastFileProcessWorker starting up...")

    while not shutdown.requested:
        if not db.ping():
            raise RuntimeError("Lost connection to database")

        popped = client.brpop(queue.FILE_QUEUE, timeout=queue.POP_TIMEOUT)
        if popped is None:
            continue

        _, payload = popped
        job = FileJob.from_json(payload)
        log.info("FFPW: Processing %s, %s", job.file_id, job.path)
        try:
            worker.process_file(db, job)
        except Exception:  # noqa: BLE001 - one bad file must not kill the pod
            # The Perl worker dies here and its supervisor restarts it. As a
            # Deployment that is a crash loop instead: the file stays
            # is_dicom_file null, the daemon re-queues it, and the
            # replacement pod dies on the same file. Log and move on.
            log.exception("FFPW: ERROR failed to process %s", job.file_id)
        # Hand the same payload to the pixel pass. A file that failed above
        # is still forwarded, as it is in the Perl, because the two passes
        # read the file independently.
        client.rpush(queue.PIXEL_QUEUE, payload)

    log.info("FFPW: Worker stopping.")
    db.close()


def run_pixel_worker() -> None:
    """Port of the FastPixelInfoWorker.pl main loop."""
    shutdown = ShutdownFlag().install()
    db = Database("posda_files")
    client = queue.connect()
    log.info("FPIW: FastPixelInfoWorker starting up...")

    while not shutdown.requested:
        if not db.ping():
            raise RuntimeError("Lost connection to database")

        popped = client.brpop(queue.PIXEL_QUEUE, timeout=queue.POP_TIMEOUT)
        if popped is None:
            continue

        _, payload = popped
        job = FileJob.from_json(payload)
        log.info("FPIW: Processing %s, %s", job.file_id, job.path)
        try:
            pixel_worker.populate_pixel_info(db, job)
        except Exception:  # noqa: BLE001 - matches the Perl's eval
            # The Perl wraps this call in eval and logs the failure so a
            # single unreadable file cannot stop the worker.
            log.exception("FPIW: ERROR failed to process %s", job.file_id)

    log.info("FPIW: Worker stopping.")
    db.close()


ROLES = {
    "daemon": run_daemon,
    "file-worker": run_file_worker,
    "pixel-worker": run_pixel_worker,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=sorted(ROLES), default="daemon", nargs="?")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    ROLES[args.role]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
