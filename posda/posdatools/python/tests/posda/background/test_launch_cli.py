import json

import pytest

from posda.background import launch as L
from posda.background import launch_cli as cli

OP = L.Operation(
    operation_name="HelloWorldPython",
    command_line="BackgroundHelloWorldWithInput.py <?bkgrnd_id?> <activity_id> <notify>",
    operation_type="background_process",
    input_line_format="<series_instance_uid>",
    tags=["test"],
    worker_priority=1,
)


@pytest.fixture
def stack(monkeypatch):
    """Replace the environment-bound pieces with recorders."""
    calls = {"launched": [], "pushed": [], "list_tag": []}
    monkeypatch.setattr(cli, "connect", lambda: "conn")
    monkeypatch.setattr(cli, "load_operation", lambda conn, name: _lookup(name))
    monkeypatch.setattr(
        cli, "list_operations", lambda conn, tag: calls["list_tag"].append(tag) or [OP]
    )

    def fake_launch(conn, plan, *, import_file, push_work):
        calls["launched"].append(plan)
        return L.LaunchResult(
            5, 6, plan.operation.queue_name, 1, 2, 3, plan.expanded_command
        )

    monkeypatch.setattr(cli, "launch", fake_launch)
    return calls


def _lookup(name):
    if name == OP.operation_name:
        return OP
    raise L.UnknownOperationError(name)


def test_collect_params_accepts_both_forms():
    params = cli.collect_params(
        ["a=1", "eq=x=y"], ["--b", "two words", "--c=3", "--d", "-1"]
    )
    assert params == {"a": "1", "eq": "x=y", "b": "two words", "c": "3", "d": "-1"}


@pytest.mark.parametrize(
    "pairs, extras, message",
    [
        (["novalue"], [], "NAME=VALUE"),
        (["a=1"], ["--a", "2"], "more than once"),
        ([], ["stray"], "unexpected argument"),
        ([], ["--flag"], "needs a value"),
        ([], ["--flag", "--other", "x"], "needs a value"),
    ],
)
def test_collect_params_rejects_malformed_input(pairs, extras, message):
    with pytest.raises(L.ParameterError, match=message):
        cli.collect_params(pairs, extras)


def test_describe(stack, capsys):
    assert cli.main(["HelloWorldPython", "--describe"]) == 0
    out = capsys.readouterr().out
    assert "Parameters:  activity_id, notify" in out
    assert "Queue:       work_queue_1 (priority 1)" in out
    assert "<series_instance_uid>" in out
    assert stack["launched"] == []


def test_describe_json(stack, capsys):
    assert cli.main(["HelloWorldPython", "--describe", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["parameters"] == ["activity_id", "notify"]
    assert data["input_fields"] == ["series_instance_uid"]


def test_list(stack, capsys):
    assert cli.main(["--list", "--tag", "test"]) == 0
    assert "HelloWorldPython" in capsys.readouterr().out
    assert stack["list_tag"] == ["test"]


def test_missing_parameters_abort_before_launch(stack, capsys):
    assert cli.main(["HelloWorldPython", "--activity_id", "1"]) == cli.EXIT_USAGE
    assert "missing parameters: notify" in capsys.readouterr().err
    assert stack["launched"] == []


def test_unknown_operation(stack, capsys):
    assert cli.main(["Nope", "-p", "a=1"]) == cli.EXIT_FAILURE
    assert "no spreadsheet operation named 'Nope'" in capsys.readouterr().err


def test_no_operation_is_a_usage_error(stack):
    with pytest.raises(SystemExit) as exc:
        cli.main(["-p", "a=1"])
    assert exc.value.code == 2


def test_launch_with_stdin_file(stack, tmp_path, capsys):
    lines = tmp_path / "in.txt"
    lines.write_text("1.1\n\n2.2\n")
    rc = cli.main(
        [
            "HelloWorldPython",
            "--activity_id",
            "7",
            "-p",
            "notify=me",
            "--stdin",
            str(lines),
            "--invoking-user",
            "quasar",
            "--json",
        ]
    )
    assert rc == 0
    (plan,) = stack["launched"]
    assert plan.params == {"activity_id": "7", "notify": "me"}
    assert plan.input_lines == ["1.1", "2.2"]
    assert plan.user == "quasar"
    data = json.loads(capsys.readouterr().out)
    assert data["work_id"] == 6 and data["subprocess_invocation_id"] == 5
    assert data["command_line"] == "BackgroundHelloWorldWithInput.py <?bkgrnd_id?> 7 me"


def test_launch_reads_dash_as_this_stdin(stack, monkeypatch):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("9.9\n"))
    assert (
        cli.main(
            [
                "HelloWorldPython",
                "-p",
                "activity_id=1",
                "-p",
                "notify=n",
                "--stdin",
                "-",
            ]
        )
        == 0
    )
    assert stack["launched"][0].input_lines == ["9.9"]


def test_dry_run_does_not_launch_but_warns_about_missing_input(stack, capsys):
    rc = cli.main(
        ["HelloWorldPython", "-p", "activity_id=1", "-p", "notify=n", "--dry-run"]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert (
        "Command:     BackgroundHelloWorldWithInput.py <?bkgrnd_id?> 1 n"
        in captured.out
    )
    assert "expects input lines" in captured.err
    assert stack["launched"] == []


def test_not_launchable_operation(stack, monkeypatch, capsys):
    legacy = L.Operation("Old", "Old.pl <a>", "legacy", None)
    monkeypatch.setattr(cli, "load_operation", lambda conn, name: legacy)
    assert cli.main(["Old", "-p", "a=1"]) == cli.EXIT_FAILURE
    assert "operation_type 'legacy'" in capsys.readouterr().err


def test_launch_with_csv_file(stack, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("ignored,series_instance_uid\nx,1.1\ny,2.2\n")
    rc = cli.main(
        [
            "HelloWorldPython",
            "-p",
            "activity_id=1",
            "-p",
            "notify=n",
            "--csv",
            str(source),
        ]
    )
    assert rc == 0
    (plan,) = stack["launched"]
    assert plan.input_lines == ["1.1", "2.2"]
    assert plan.input_cells == [["1.1"], ["2.2"]]


def test_csv_missing_column_aborts_before_launch(stack, tmp_path, capsys):
    source = tmp_path / "in.csv"
    source.write_text("sop\n1.1\n")
    rc = cli.main(
        [
            "HelloWorldPython",
            "-p",
            "activity_id=1",
            "-p",
            "notify=n",
            "--csv",
            str(source),
        ]
    )
    assert rc == cli.EXIT_USAGE
    assert "missing columns: series_instance_uid" in capsys.readouterr().err
    assert stack["launched"] == []


def test_stdin_and_csv_are_exclusive(stack):
    with pytest.raises(SystemExit) as exc:
        cli.main(["HelloWorldPython", "--stdin", "a", "--csv", "b"])
    assert exc.value.code == 2
