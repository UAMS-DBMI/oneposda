"""Port of ``FastFileProcessDaemon.pl`` and the worker run loops.

The daemon does two jobs: refill the Redis ``files`` list from the database
whenever it drains, and supervise the worker processes. Both worker loops
live here too since they are a handful of lines each and share the same
shutdown convention.

The replenish query, batch size and poll intervals are kept as they are in
the Perl -- 1000 rows per refill, a 1s tick, and a 10s pause when the
database has nothing to offer.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import signal
import sys
import time

from posda.ingest import pixel_worker, queue, worker
from posda.ingest.db import Database
from posda.ingest.worker import FileJob

log = logging.getLogger(__name__)

WORKER_COUNT = 5
BATCH_SIZE = 1000
IDLE_SLEEP = 10
TICK = 1
POP_TIMEOUT = 5

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


def run_daemon(spawn_workers: bool = True) -> None:
    db = Database("posda_files")
    client = queue.connect()

    log.info("FFPD: FastFileProcessDaemon starting up...")
    # Clear any stale shutdown flag so the workers we are about to start do
    # not immediately exit.
    queue.clear_shutdown(client)

    children: list[multiprocessing.Process] = []
    if spawn_workers:
        children = _start_workers()

    def shut_down(*_args: object) -> None:
        log.info("FFPD: Shutdown signal received, exiting now. Goodbye!")
        queue.request_shutdown(client)
        for child in children:
            child.join(timeout=30)
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shut_down)
    signal.signal(signal.SIGTERM, shut_down)

    while True:
        if not db.ping():
            raise RuntimeError("Lost connection to database")

        if client.llen(queue.FILE_QUEUE) == 0:
            count = replenish(db, client)
            if count:
                log.info("FFPD: Added %d files to the queue.", count)
            else:
                time.sleep(IDLE_SLEEP)

        if queue.should_quit(client):
            shut_down()

        time.sleep(TICK)


def _start_workers() -> list[multiprocessing.Process]:
    children = []
    for _ in range(WORKER_COUNT):
        child = multiprocessing.Process(target=run_file_worker, daemon=True)
        child.start()
        children.append(child)
    for _ in range(WORKER_COUNT):
        child = multiprocessing.Process(target=run_pixel_worker, daemon=True)
        child.start()
        children.append(child)
    return children


def run_file_worker() -> None:
    """Port of the FastFileProcessWorker.pl main loop."""
    db = Database("posda_files")
    client = queue.connect()
    log.info("FFPW: FastFileProcessWorker starting up...")

    while True:
        if not db.ping():
            raise RuntimeError("Lost connection to database")

        popped = client.brpop(queue.FILE_QUEUE, timeout=POP_TIMEOUT)
        if popped is not None:
            _, payload = popped
            job = FileJob.from_json(payload)
            log.info("FFPW: Processing %s, %s", job.file_id, job.path)
            worker.process_file(db, job)
            # Hand the same payload to the pixel pass.
            client.rpush(queue.PIXEL_QUEUE, payload)

        if queue.should_quit(client):
            log.info("FFPW: Worker stopping.")
            db.close()
            return


def run_pixel_worker() -> None:
    """Port of the FastPixelInfoWorker.pl main loop."""
    db = Database("posda_files")
    client = queue.connect()
    log.info("FPIW: FastPixelInfoWorker starting up...")

    while True:
        if not db.ping():
            raise RuntimeError("Lost connection to database")

        popped = client.brpop(queue.PIXEL_QUEUE, timeout=POP_TIMEOUT)
        if popped is not None:
            _, payload = popped
            job = FileJob.from_json(payload)
            log.info("FPIW: Processing %s, %s", job.file_id, job.path)
            try:
                pixel_worker.populate_pixel_info(db, job)
            except Exception as exc:  # noqa: BLE001 - matches the Perl's eval
                # The Perl wraps this call in eval and logs the failure so a
                # single unreadable file cannot stop the worker.
                log.error("FPIW: ERROR failed to process %s: %s", job.file_id, exc)

        if queue.should_quit(client):
            log.info("FPIW: Worker stopping.")
            db.close()
            return


ROLES = {
    "daemon": run_daemon,
    "file-worker": run_file_worker,
    "pixel-worker": run_pixel_worker,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=sorted(ROLES), default="daemon", nargs="?")
    parser.add_argument(
        "--no-workers",
        action="store_true",
        help="run the daemon without spawning workers (they are separate "
        "processes or containers)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.role == "daemon":
        run_daemon(spawn_workers=not args.no_workers)
    else:
        ROLES[args.role]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
