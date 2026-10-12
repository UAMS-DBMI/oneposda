import logging

import pytest

from posda.worker import cli


@pytest.fixture
def modes(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.legacy, "run_legacy", lambda: calls.append("legacy"))
    monkeypatch.setattr(
        cli.dispatch, "run_dispatcher", lambda: calls.append("dispatch")
    )
    monkeypatch.setattr(
        cli.run, "run_single", lambda wid: calls.append(("run", wid)) or 7
    )
    return calls


def test_no_arguments_is_the_legacy_loop(modes):
    assert cli.main([]) == 0
    assert modes == ["legacy"]


def test_dispatch(modes):
    assert cli.main(["dispatch"]) == 0
    assert modes == ["dispatch"]


def test_run_returns_the_worker_exit_code(modes):
    assert cli.main(["run", "42"]) == 7
    assert modes == [("run", 42)]


def test_run_rejects_a_non_integer_id(modes):
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "abc"])
    assert exc.value.code == 2
    assert modes == []


def test_log_format_is_the_legacy_one():
    assert (
        cli.LOG_FORMAT == "[%(levelname).4s|%(asctime)s|%(module)-15.15s] %(message)s"
    )
