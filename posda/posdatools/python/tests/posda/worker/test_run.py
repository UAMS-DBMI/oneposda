import pytest

from fakes import FakePosdaApi
from posda.worker import run
from posda.worker.settings import WorkerSettings


@pytest.fixture
def wired(monkeypatch):
    def _wire(api, process=None):
        monkeypatch.setattr(
            run,
            "load_worker_settings",
            lambda: WorkerSettings("http://web/papi", "redis", "1", "pod-x", "tok"),
        )
        monkeypatch.setattr(run, "PosdaApi", lambda base_url, token: api)
        if process is not None:
            monkeypatch.setattr(run.execute, "process_work_item", process)
        return api

    return _wire


def fresh_item():
    return {5: {"work_id": 5, "running": False, "finished": False, "failed": False}}


def test_processed_item_exits_0_even_when_the_script_failed(wired):
    api = wired(FakePosdaApi(work_items=fresh_item()), process=lambda api, wid, node: 3)
    assert run.run_single(5) == run.EXIT_OK


def test_worker_failure_reports_errored_and_exits_1(wired):
    def explode(api, wid, node):
        raise RuntimeError("api down")

    api = wired(FakePosdaApi(work_items=fresh_item()), process=explode)
    assert run.run_single(5) == run.EXIT_WORK_FAILED
    assert api.statuses == [
        ("errored", 5, None, None, {"worker_error": "RuntimeError('api down')"})
    ]


def test_unreportable_failure_exits_2(wired):
    def explode(api, wid, node):
        api.fail_status = True
        raise RuntimeError("api down")

    wired(FakePosdaApi(work_items=fresh_item()), process=explode)
    assert run.run_single(5) == run.EXIT_REPORT_FAILED


@pytest.mark.parametrize("flag", ["running", "finished", "failed"])
def test_already_started_item_is_refused(wired, flag):
    items = fresh_item()
    items[5][flag] = True
    ran = []
    api = wired(FakePosdaApi(work_items=items), process=lambda *a: ran.append(a))
    assert run.run_single(5) == run.EXIT_ALREADY_STARTED
    assert ran == [] and api.statuses == []


def test_passes_the_pod_name_as_node_hostname(wired):
    seen = []
    wired(
        FakePosdaApi(work_items=fresh_item()),
        process=lambda api, wid, node: seen.append((wid, node)),
    )
    run.run_single(5)
    assert seen == [(5, "pod-x")]


def test_missing_api_url_fails_early(monkeypatch):
    monkeypatch.setattr(
        run,
        "load_worker_settings",
        lambda: WorkerSettings(None, "redis", "1", "n", None),
    )
    with pytest.raises(RuntimeError, match="POSDA_INTERNAL_API_URL"):
        run.run_single(5)
