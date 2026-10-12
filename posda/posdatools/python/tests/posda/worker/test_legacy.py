import os
import signal

import pytest

from fakes import FakePosdaApi, FakeRedis
from posda.worker import legacy


def stop_after(n):
    count = {"n": 0}

    def _hook():
        count["n"] += 1
        if count["n"] > n:
            os.kill(os.getpid(), signal.SIGTERM)

    return _hook


class TestRestartIfNeeded:
    def test_unset_key_is_ignored(self):
        legacy.restart_if_needed(FakeRedis())

    def test_non_integer_is_ignored(self, caplog):
        legacy.restart_if_needed(FakeRedis(values={"worker-node-version": "x"}))
        assert "not an integer" in caplog.text

    def test_same_version_keeps_running(self):
        legacy.restart_if_needed(
            FakeRedis(values={"worker-node-version": str(legacy.VERSION)})
        )

    def test_newer_version_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            legacy.restart_if_needed(
                FakeRedis(values={"worker-node-version": str(legacy.VERSION + 1)})
            )
        assert exc.value.code == 1


class TestWorkLoop:
    def test_processes_items_from_its_queue_then_stops_on_sigterm(self, monkeypatch):
        legacy.install_sigterm_handler()
        redis_db = FakeRedis(queues={"work_queue_1": ["8", "7"], "work_queue_0": ["1"]})
        redis_db.on_pop = stop_after(2)
        seen = []
        monkeypatch.setattr(
            legacy.execute,
            "process_work_item",
            lambda api, wid, node: seen.append((wid, node)),
        )

        with pytest.raises(legacy.SigTerm):
            legacy.work_loop(redis_db, "work_queue_1", FakePosdaApi(), "node-z")

        assert seen == [("7", "node-z"), ("8", "node-z")]
        assert redis_db.lists["work_queue_0"] == ["1"]

    def test_failure_marks_the_item_errored_and_continues(self, monkeypatch):
        legacy.install_sigterm_handler()
        redis_db = FakeRedis(queues={"work_queue_0": ["2", "1"]})
        redis_db.on_pop = stop_after(2)
        api = FakePosdaApi()

        def explode(api, wid, node):
            raise RuntimeError("nope")

        monkeypatch.setattr(legacy.execute, "process_work_item", explode)
        with pytest.raises(legacy.SigTerm):
            legacy.work_loop(redis_db, "work_queue_0", api, "n")

        assert api.statuses == [
            ("errored", 1, None, None, None),
            ("errored", 2, None, None, None),
        ]

    def test_timeout_keeps_polling(self):
        legacy.install_sigterm_handler()
        redis_db = FakeRedis()
        redis_db.on_pop = stop_after(3)
        with pytest.raises(legacy.SigTerm):
            legacy.work_loop(redis_db, "work_queue_0", FakePosdaApi(), "n")
        assert redis_db.pops == 4
