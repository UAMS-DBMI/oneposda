"""Tests for the run loops and their shutdown behaviour.

These cover the parts that make the three roles safe to run as separate,
independently restarted containers: each process stops on its own SIGTERM
without touching the others, and a single unparseable file cannot take a
worker down.
"""

import json
import os
import signal
import threading

import pytest

from posda.ingest import daemon, lifecycle, queue
from posda.ingest.worker import FileJob


class FakeRedis:
    """Just enough of redis.Redis for the run loops.

    ``brpop`` returns queued items and then blocks-by-returning-None, which
    is what the real client does when its timeout expires on an empty list.
    """

    def __init__(self, files=(), pixels=()):
        self.lists = {
            queue.FILE_QUEUE: list(files),
            queue.PIXEL_QUEUE: list(pixels),
        }
        self.on_pop = None

    def llen(self, key):
        return len(self.lists.get(key, []))

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def brpop(self, key, timeout=None):
        items = self.lists.get(key, [])
        if self.on_pop is not None:
            self.on_pop()
        if not items:
            return None
        return key, items.pop()


class FakeDatabase:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.closed = False

    def ping(self):
        return True

    def fetchall(self, sql, params=()):
        limit = params[0]
        return iter(self.rows[:limit])

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def restore_signal_handlers():
    """Put pytest's handlers back; the run loops install their own."""
    saved = [(sig, signal.getsignal(sig)) for sig in (signal.SIGINT, signal.SIGTERM)]
    yield
    for sig, handler in saved:
        signal.signal(sig, handler)


@pytest.fixture
def wired(monkeypatch):
    """Point a run loop at fakes and hand both back to the test."""

    def _wire(db, client):
        monkeypatch.setattr(daemon, "Database", lambda *a, **k: db)
        monkeypatch.setattr(daemon.queue, "connect", lambda *a, **k: client)
        return db, client

    return _wire


class TestShutdownFlag:
    def test_starts_clear_and_sets_on_signal(self):
        flag = lifecycle.ShutdownFlag()
        assert not flag.requested
        flag._request(signal.SIGTERM, None)
        assert flag.requested

    def test_sleep_returns_early_once_requested(self):
        flag = lifecycle.ShutdownFlag()
        threading.Timer(0.05, flag._request, [signal.SIGTERM, None]).start()
        # Would block for 30s if the flag were ignored.
        flag.sleep(30)
        assert flag.requested

    def test_sigterm_stops_only_this_process(self, wired):
        """No Redis key is written, so other pods keep running.

        The Perl signals shutdown by setting 'quit' in Redis, which every
        worker polls. That is what made the tiers inseparable.
        """
        db, client = wired(FakeDatabase(), FakeRedis())
        client.on_pop = lambda: os.kill(os.getpid(), signal.SIGTERM)

        daemon.run_file_worker()

        assert client.lists == {queue.FILE_QUEUE: [], queue.PIXEL_QUEUE: []}
        assert db.closed


class TestFileWorker:
    def test_forwards_the_payload_to_the_pixel_queue(self, wired, monkeypatch):
        payload = FileJob(file_id=7, path="/a/b.dcm").to_json()
        db, client = wired(FakeDatabase(), FakeRedis(files=[payload]))
        seen = []
        monkeypatch.setattr(
            daemon.worker, "process_file", lambda _db, job: seen.append(job)
        )
        client.on_pop = _stop_after(1)

        daemon.run_file_worker()

        assert [job.file_id for job in seen] == [7]
        assert client.lists[queue.PIXEL_QUEUE] == [payload]

    def test_a_failing_file_does_not_stop_the_worker(self, wired, monkeypatch):
        """A crash here would be a CrashLoopBackOff, not a restarted worker.

        The file stays is_dicom_file null, so the daemon re-queues it and the
        replacement pod dies on the same file, forever.
        """
        payloads = [FileJob(i, f"/{i}.dcm").to_json() for i in (1, 2)]
        db, client = wired(FakeDatabase(), FakeRedis(files=payloads))
        seen = []

        def explode_on_the_first(_db, job):
            seen.append(job.file_id)
            if job.file_id == 2:
                raise ValueError("unreadable")

        monkeypatch.setattr(daemon.worker, "process_file", explode_on_the_first)
        client.on_pop = _stop_after(2)

        daemon.run_file_worker()

        # brpop takes from the tail, so file 2 -- the one that raised -- is
        # popped first and the worker still gets to file 1.
        assert seen == [2, 1]
        assert client.lists[queue.PIXEL_QUEUE] == list(reversed(payloads))


class TestPixelWorker:
    def test_a_failing_file_does_not_stop_the_worker(self, wired, monkeypatch):
        payload = FileJob(3, "/3.dcm").to_json()
        db, client = wired(FakeDatabase(), FakeRedis(pixels=[payload]))

        def explode(_db, _job):
            raise ValueError("unreadable")

        monkeypatch.setattr(daemon.pixel_worker, "populate_pixel_info", explode)
        client.on_pop = _stop_after(1)

        daemon.run_pixel_worker()

        assert db.closed


class TestReplenish:
    def test_queues_pending_files_in_the_perl_payload_format(self):
        client = FakeRedis()
        db = FakeDatabase([{"file_id": 4, "path": "/x/y.dcm"}])

        assert daemon.replenish(db, client) == 1
        assert json.loads(client.lists[queue.FILE_QUEUE][0]) == [4, "/x/y.dcm"]

    def test_honours_the_batch_size(self, monkeypatch):
        monkeypatch.setattr(daemon, "BATCH_SIZE", 2)
        db = FakeDatabase([{"file_id": i, "path": f"/{i}"} for i in range(5)])

        assert daemon.replenish(db, FakeRedis()) == 2


def _stop_after(pops):
    """Raise SIGTERM once the loop has taken `pops` items off the queue."""
    remaining = [pops]

    def hook():
        remaining[0] -= 1
        if remaining[0] < 0:
            os.kill(os.getpid(), signal.SIGTERM)

    return hook
