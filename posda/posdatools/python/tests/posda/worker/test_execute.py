import os
import stat
import subprocess

import pytest

from fakes import FakePosdaApi
from posda.worker import execute

TIME_SHIM = """#!/bin/sh
# Stand-in for GNU time: consume "-v -o FILE", write a fake report, run the rest.
shift; shift
out=$1; shift
printf '\\tCommand being timed: "fake"\\n\\tMaximum resident set size (kbytes): 1234\\n\\tExit status: 0\\n' > "$out"
exec "$@"
"""


@pytest.fixture
def time_shim(tmp_path, monkeypatch):
    shim = tmp_path / "time"
    shim.write_text(TIME_SHIM)
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(execute, "TIME_BINARY", str(shim))
    monkeypatch.setattr(
        execute, "timefile_path", lambda wid: str(tmp_path / f"{wid}.time")
    )
    return shim


def make_api(command_line, stdin_text="", tmp_path=None):
    stdin_file = tmp_path / "input.csv"
    stdin_file.write_text(stdin_text)
    return FakePosdaApi(
        work_items={
            5: {"work_id": 5, "subprocess_invocation_id": 9, "input_file_id": 3}
        },
        subprocesses={9: {"subprocess_invocation_id": 9, "command_line": command_line}},
        paths={3: str(stdin_file)},
    )


class TestParseTimefile:
    def test_parses_and_unlinks(self, tmp_path):
        f = tmp_path / "t"
        f.write_text(
            '\tCommand being timed: "ls -l"\n\tElapsed (wall clock) time (h:mm:ss or m:ss): 0:00.01\n\tExit status: 0\nmalformed line\n'
        )
        assert execute.parse_timefile(str(f)) == {
            "Command being timed": '"ls -l"',
            "Elapsed (wall clock) time (h:mm:ss or m:ss)": "0:00.01",
            "Exit status": "0",
        }
        assert not f.exists()

    def test_missing_file_is_none(self, tmp_path):
        assert execute.parse_timefile(str(tmp_path / "nope")) is None


def test_build_command_line_substitutes_the_background_id(monkeypatch):
    monkeypatch.setattr(execute, "TIME_BINARY", "/usr/bin/time")
    subp = {"subprocess_invocation_id": 42, "command_line": "Foo.pl <?bkgrnd_id?> x"}
    assert (
        execute.build_command_line(subp, "/tmp/5.time")
        == "/usr/bin/time -v -o /tmp/5.time Foo.pl 42 x"
    )


def test_capture_file_child_appends_regardless_of_parent_offset():
    wfd, rfp = execute.make_capture_file()
    try:
        os.write(wfd, b"first\n")
        assert rfp.read() == b"first\n"
        rfp.seek(0)
        os.write(wfd, b"second\n")  # must not overwrite "first"
        assert rfp.read() == b"first\nsecond\n"
    finally:
        os.close(wfd)
        rfp.close()


def test_kill_process_group_reaps_orphans():
    # The shell exits at once, leaving `sleep` orphaned in the shell's group,
    # which is exactly what a background script's forked children do.
    proc = subprocess.Popen("sleep 30 & exit 0", shell=True, start_new_session=True)
    proc.wait()
    os.killpg(proc.pid, 0)  # the orphan keeps the group alive
    execute.kill_process_group(proc.pid, grace_seconds=2)
    with pytest.raises(ProcessLookupError):
        os.killpg(proc.pid, 0)


class TestProcessWorkItem:
    def test_success_path(self, tmp_path, time_shim):
        api = make_api("cat; echo warn >&2", stdin_text="in-data\n", tmp_path=tmp_path)
        rc = execute.process_work_item(api, "5", "node-a")
        assert rc == 0
        assert api.running_calls == [(5, "node-a")]
        assert api.uploads == [b"in-data\n", b"warn\n"]
        status, work_id, stderr_id, stdout_id, metrics = api.statuses[0]
        assert (status, work_id, stdout_id, stderr_id) == ("finished", 5, 1, 2)
        assert metrics["Maximum resident set size (kbytes)"] == "1234"

    def test_non_zero_exit_is_errored(self, tmp_path, time_shim):
        api = make_api("sh -c 'exit 3'", tmp_path=tmp_path)
        assert execute.process_work_item(api, 5, "n") == 3
        assert api.statuses[0][0] == "errored"

    def test_upload_failure_still_reports(self, tmp_path, time_shim, caplog):
        api = make_api("echo out; echo err >&2", tmp_path=tmp_path)
        api.fail_upload = True
        execute.process_work_item(api, 5, "n")
        status, _, stderr_id, stdout_id, _ = api.statuses[0]
        assert (status, stderr_id, stdout_id) == ("finished", None, None)
        assert "Could not upload" in caplog.text
        assert "b'err\\n'" in caplog.text and "b'out\\n'" in caplog.text

    def test_unknown_work_id_raises_before_running_anything(self, tmp_path, time_shim):
        api = FakePosdaApi()
        with pytest.raises(RuntimeError, match="No such work_id"):
            execute.process_work_item(api, 99, "n")
        assert api.statuses == []
