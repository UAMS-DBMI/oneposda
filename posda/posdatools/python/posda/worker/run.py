"""Job entrypoint: process exactly one work item, report, exit.

Exit codes are about the *worker*, not the script it ran. A script that
exits non-zero is reported to Posda as errored and this process still exits
0: the Job did its job. The Job only Fails when the worker could not process
or report the item at all, which is what the dispatcher's reconcile pass
looks for.
"""

from __future__ import annotations

import logging

from posda.worker import execute
from posda.worker.api import PosdaApi
from posda.worker.legacy import SigTerm, install_sigterm_handler
from posda.worker.settings import load_worker_settings, require_api_url

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_WORK_FAILED = 1
EXIT_REPORT_FAILED = 2
EXIT_ALREADY_STARTED = 3


def run_single(work_id: int) -> int:
    install_sigterm_handler()
    settings = load_worker_settings()
    require_api_url(settings)
    api = PosdaApi(settings.base_url, settings.api_token)

    try:
        if already_started(api, work_id):
            return EXIT_ALREADY_STARTED
        execute.process_work_item(api, work_id, settings.node_name)
        return EXIT_OK
    except SigTerm:
        log.error("SIGTERM while processing work item %s", work_id)
        report_worker_error(api, work_id, "SIGTERM")
        raise
    except Exception as exc:
        log.exception("could not process work item %s", work_id)
        if report_worker_error(api, work_id, repr(exc)):
            return EXIT_WORK_FAILED
        return EXIT_REPORT_FAILED


def already_started(api: PosdaApi, work_id: int) -> bool:
    """Refuse to run a work item a previous pod already picked up.

    Kueue can delete a Job's pods without counting a failure (HoldAndDrain,
    preemption) and re-admit it later; the fresh pod would otherwise run a
    non-idempotent background script a second time. Refusing makes the Job
    Fail, and the dispatcher's reconcile marks the row errored.
    """
    item = api.get_work_item(work_id)
    if item.get("running") or item.get("finished") or item.get("failed"):
        log.error(
            "work item %s was already started (status=%s, node=%s); not re-running",
            work_id,
            item.get("status"),
            item.get("node_hostname"),
        )
        return True
    return False


def report_worker_error(api: PosdaApi, work_id: int, reason: str) -> bool:
    """Mark the row errored with the worker-side reason; False if that failed."""
    try:
        api.set_status_errored(work_id, None, None, {"worker_error": reason})
    except Exception:
        log.exception("could not report work item %s as errored", work_id)
        return False
    return True
