"""Dispatch RT module handlers to the legacy Perl implementation.

The RT handlers in ``Posda::DB::Modules`` are about 2,000 lines that lean
entirely on ``Posda::Dataset``'s sequence navigation -- all 353 of the
``(3006,0010)[<0>](3006,00c0)`` style signatures in the file are in the RT
region. Rather than port that machinery before anything else could ship,
Python runs the leading non-RT handlers and hands the trailing RT block to
``Posda/bin/PosdaIngestRtBridge.pl``.

Three facts make the split safe, each checked against the Perl:

- Only three SOP classes use RT handlers (RT Dose, RT Structure Set,
  RT Plan).
- In all three, the RT handlers form a contiguous trailing block: no
  non-stub handler ever runs after one.
- The only ``hist`` key the RT handlers read from outside their own group is
  ``image_id``, which RTDose uses and Python's ImagePixel publishes.

Cost is one Perl startup per RT file, measured at ~0.25s in the target
image. RT files are a small fraction of a typical import; if that changes,
this can become a persistent process behind the same interface.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from posda.ingest.parse import ParseResult

log = logging.getLogger(__name__)

BRIDGE_SCRIPT = "PosdaIngestRtBridge.pl"

# Generous: RtBeams on a large plan does a lot of inserts.
DEFAULT_TIMEOUT = 600

# Only these survive the round trip into the Perl $hist.
_FORWARDED_HIST_KEYS = ("image_id",)


class RtBridgeError(RuntimeError):
    """The bridge could not be run, or failed before running handlers."""


def bridge_path() -> str:
    """Locate the bridge script on PATH, as the Perl bin directory is there."""
    found = shutil.which(BRIDGE_SCRIPT)
    if found:
        return found
    # Fall back to POSDA_ROOT/Posda/bin for callers with a bare environment.
    root = os.environ.get("POSDA_ROOT")
    if root:
        candidate = os.path.join(root, "Posda", "bin", BRIDGE_SCRIPT)
        if os.path.isfile(candidate):
            return candidate
    raise RtBridgeError(f"could not locate {BRIDGE_SCRIPT} on PATH")


def run_handlers(
    file_id: int,
    path: str,
    handlers: list[str],
    hist: dict,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[str]:
    """Run the named RT handlers in Perl; return the errors they produced.

    Errors come back rather than being written by the Perl so that the
    Python side can flush all of a file's complaints into
    ``dicom_process_errors`` in one place, preserving the Perl's ordering.
    """
    if not handlers:
        return []

    request = {
        "file_id": file_id,
        "path": path,
        "handlers": handlers,
        "hist": {
            key: hist[key] for key in _FORWARDED_HIST_KEYS if hist.get(key) is not None
        },
    }

    try:
        completed = subprocess.run(
            ["perl", bridge_path()],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [f"rt_bridge: timed out after {timeout}s on file {file_id}"]

    if completed.stderr.strip():
        log.debug("rt_bridge stderr for %s: %s", file_id, completed.stderr.strip())

    if not completed.stdout.strip():
        return [
            f"rt_bridge: no response for file {file_id} "
            f"(exit {completed.returncode})"
        ]

    try:
        response = json.loads(completed.stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return [f"rt_bridge: unparseable response for file {file_id}: {exc}"]

    # Publish anything scalar the Perl added, so later handlers (currently
    # none, but the ordering is not guaranteed forever) can see it.
    for key, value in (response.get("hist") or {}).items():
        hist.setdefault(key, value)

    return list(response.get("errors") or [])


def run_block(
    values, file_id: int, handlers: list[str], hist: dict, errors: list[str]
) -> None:
    """Run a whole RT block in one Perl call.

    Batching is not an optimisation, it is required for correctness:
    ``StructureSet`` builds ``$hist->{roi}`` and ``$hist->{ss_for_by_item}``
    for ``RoiContour`` and ``RtRoiObservations`` to consume, and those are
    nested structures that do not survive a round trip through the bridge's
    JSON. All the handlers that share them must run in the same process.
    """
    path = getattr(values, "source_path", None)
    if path is None:
        errors.append(
            f"rt_bridge: no source path for file {file_id}, "
            f"{', '.join(handlers)} skipped"
        )
        return
    errors.extend(run_handlers(file_id, path, handlers, hist))
