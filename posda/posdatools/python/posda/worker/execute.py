"""Run one work item: execute its command line, capture output, report.

This is the part of the worker that is the same in every mode. It talks only
to the Posda API (through ``PosdaApi``); nothing here touches Redis or
Kubernetes. The order of operations and the capture-file handling are a port
of the original WorkerNode.py and must stay that way: the background scripts
depend on the ``<?bkgrnd_id?>`` substitution, the ``/usr/bin/time -v`` wrapper
feeds the metrics column, and the capture-file dance exists because scripts
fork children that outlive them.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
import time
from typing import BinaryIO

from posda.worker.api import PosdaApi, WorkId

log = logging.getLogger(__name__)

#: Module constant so tests can point it at a shim (macOS ``time`` has no -v).
TIME_BINARY = "/usr/bin/time"


def process_work_item(api: PosdaApi, work_id: WorkId, node_hostname: str) -> int:
    """Process a single work item and report the outcome.

    For the given work_id:
        * set the status to running
        * get the details of the work item, and subprocess invocation
        * generate the command_line and execute it
        * record stderr and stdout, upload to posda
        * set the status to finished or errored, depending on return code

    Returns the script's return code. Raises if the worker itself could not
    do its job (API unreachable, unknown ids, ...); the caller decides how to
    report that.
    """
    log.info("new work item %s", work_id)

    api.set_status_running(work_id, node_hostname)
    work_item = api.get_work_item(work_id)
    subp = api.get_subprocess_info(work_item["subprocess_invocation_id"])

    timefile = timefile_path(work_id)
    command_line = build_command_line(subp, timefile)
    log.debug(command_line)

    stdout_wfd, stdout_fp = make_capture_file()
    stderr_wfd, stderr_fp = make_capture_file()

    stdin_path = api.get_path_from_file_id(work_item["input_file_id"])

    return_code, pid = run_command(command_line, stdin_path, stdout_wfd, stderr_wfd)
    log.info("Subprocess returned: %s", return_code)

    # Background scripts fork children that inherit these capture files and are
    # not killed when their parent exits -- they reparent to init and keep
    # running. Left alone they go on writing into the files we are about to
    # hash, upload and close, so the upload sees a moving target and everything
    # written after it is lost with the (unlinked, unnamed) inode. Reap the
    # whole group before reading anything.
    kill_process_group(pid)

    stdout_file_id, stderr_file_id = upload_captures(api, stdout_fp, stderr_fp)
    metrics = parse_timefile(timefile)

    report_result(api, work_id, return_code, stderr_file_id, stdout_file_id, metrics)
    return return_code


def timefile_path(work_id: WorkId) -> str:
    return f"/tmp/{work_id}.time"


def build_command_line(subp: dict, timefile: str) -> str:
    command_line = subp["command_line"].replace(
        "<?bkgrnd_id?>", str(subp["subprocess_invocation_id"])
    )
    return f"{TIME_BINARY} -v -o {timefile} {command_line}"


def run_command(
    command_line: str, stdin_path: str, stdout_fd: int, stderr_fd: int
) -> tuple[int, int]:
    """Run the command line through the shell; returns (return_code, pid).

    The child gets its own session so its whole process group can be reaped
    afterwards. The write ends of the capture files and the stdin file are
    closed here whatever happens, so a failure never leaks descriptors.
    """
    stdin_fp = None
    try:
        stdin_fp = open(stdin_path)
        proc = subprocess.Popen(
            command_line,
            shell=True,
            stdin=stdin_fp,
            stdout=stdout_fd,
            stderr=stderr_fd,
            start_new_session=True,
        )
        return_code = proc.wait()
    finally:
        os.close(stdout_fd)
        os.close(stderr_fd)
        if stdin_fp is not None:
            stdin_fp.close()
    return return_code, proc.pid


def make_capture_file() -> tuple[int, BinaryIO]:
    """Create a capture file for a child's stdout or stderr.

    Returns (write_fd, read_fp) referring to the same unlinked inode through
    two *separate* open file descriptions. That separation is the point:
    tempfile.TemporaryFile() hands the same description to the child (Popen
    dups it), so the child shares our file offset -- and seek(0) to hash and
    upload would rewind it underneath any child still writing, which then
    overwrote the head of the file. The child's fd is O_APPEND so its writes
    always land at the end regardless of where we have seeked to.
    """
    fd, path = tempfile.mkstemp()
    os.close(fd)
    write_fd = None
    try:
        write_fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        read_fp = open(path, "rb")
    except Exception:
        if write_fd is not None:
            os.close(write_fd)
        os.unlink(path)
        raise
    # Unlink now so the inode cannot leak into ephemeral container storage if
    # we die before closing; both descriptors keep it alive until then.
    os.unlink(path)
    return write_fd, read_fp


def kill_process_group(pgid: int, grace_seconds: float = 5.0) -> None:
    """Terminate anything left in the child's process group.

    The child is started with start_new_session=True, which makes it a session
    and process-group leader -- so its pid *is* the group id. Do not try to
    look that up with getpgid(): by the time we are called the child itself has
    been reaped, and the lookup fails with ProcessLookupError even though its
    orphaned descendants are still running.

    Scripts that deliberately detach (posda.background.fork calls setsid) land
    in a session of their own and are intentionally left alone.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        log.warning("sent %s to leftover process group %s", sig.name, pgid)
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            time.sleep(0.1)
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return

    log.error("process group %s survived SIGKILL", pgid)


def upload_captures(
    api: PosdaApi, stdout_fp: BinaryIO, stderr_fp: BinaryIO
) -> tuple[int | None, int | None]:
    """Upload both capture files; returns (stdout_file_id, stderr_file_id).

    An upload failure is not fatal to the work item: the ids come back as
    None and the first lines of each stream go to the log so they are not
    lost entirely. Both files are closed here whatever happens.
    """
    stdout_file_id = None
    stderr_file_id = None
    try:
        stdout_file_id = api.upload_file(stdout_fp)
        stderr_file_id = api.upload_file(stderr_fp)
        log.info("stdout:%s stderr:%s", stdout_file_id, stderr_file_id)
    except Exception:
        log.exception(
            "Could not upload stdout or stderr! First 5 lines of each follow..."
        )
        stderr_fp.seek(0)
        stdout_fp.seek(0)
        for _ in range(5):
            log.error(stderr_fp.readline(500))
        for _ in range(5):
            log.error(stdout_fp.readline(500))
    finally:
        stdout_fp.close()
        stderr_fp.close()
    return stdout_file_id, stderr_file_id


def parse_timefile(filename: str) -> dict[str, str] | None:
    """Turn ``/usr/bin/time -v`` output into a dict; None if unreadable.

    The file is removed afterwards: /tmp is the container's ephemeral layer
    and these used to accumulate for the life of the pod.
    """
    try:
        with open(filename) as f:
            rows = [row.strip() for row in f]
    except Exception:
        log.warning("could not read timefile %s", filename, exc_info=True)
        return None
    finally:
        try:
            os.unlink(filename)
        except OSError:
            pass

    out_dict: dict[str, str] = {}
    for row in rows:
        try:
            key, value = row.split(": ")
        except ValueError:
            log.debug("skipping unparseable timefile row: %r", row)
            continue
        out_dict[key] = value
    return out_dict


def report_result(
    api: PosdaApi,
    work_id: WorkId,
    return_code: int,
    stderr_file_id: int | None,
    stdout_file_id: int | None,
    metrics: dict | None,
) -> None:
    if return_code != 0:
        api.set_status_errored(work_id, stderr_file_id, stdout_file_id, metrics)
    else:
        api.set_status_finished(work_id, stderr_file_id, stdout_file_id, metrics)
