"""Dispatcher: turn queued work ids into Kueue-managed Kubernetes Jobs.

Redis stays the queue of record. An id is only popped when there is room to
create a Job for it, and the Job is created in the same iteration, so the
only way to lose an item is a hard kill in between -- the same window the
legacy loop has between its BRPOP and its first API call.

Kueue decides when a Job runs. This loop never touches pending or suspended
Jobs; it only creates them and, on a timer, cleans up after the ones that
failed without reporting (OOMKilled, evicted, image pull failure ...), so the
``work`` row does not stay ``running`` forever.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import redis
import requests

from posda.ingest.lifecycle import ShutdownFlag
from posda.worker import jobspec, workqueue
from posda.worker.api import PosdaApi
from posda.worker.k8s import JobAlreadyExists, KubernetesApiError, KubernetesClient
from posda.worker.settings import (
    DispatchSettings,
    WorkerSettings,
    load_dispatch_settings,
    load_worker_settings,
    require_api_url,
)

log = logging.getLogger(__name__)


@dataclass
class ReconcileResult:
    open_jobs: int
    errored_work_ids: list[int] = field(default_factory=list)


def run_dispatcher() -> None:
    shutdown = ShutdownFlag().install()
    worker = load_worker_settings()
    require_api_url(worker)
    settings = load_dispatch_settings()

    api = PosdaApi(worker.base_url, worker.api_token)
    k8s = KubernetesClient.in_cluster(settings.namespace)
    own_pod = k8s.get_pod(settings.pod_name)  # a pod's spec is immutable
    redis_db = workqueue.connect(worker.redis_host)

    log.info(
        "dispatcher started: queue=%s kueue_queue=%s namespace=%s max_open_jobs=%s",
        worker.queue_name,
        settings.kueue_queue,
        settings.namespace,
        settings.max_open_jobs,
    )
    dispatch_loop(redis_db, api, k8s, own_pod, worker, settings, shutdown)


def dispatch_loop(
    redis_db: redis.StrictRedis,
    api: PosdaApi,
    k8s: KubernetesClient,
    own_pod: dict,
    worker: WorkerSettings,
    settings: DispatchSettings,
    shutdown: ShutdownFlag,
) -> None:
    selector = label_selector(worker.worker_priority)
    open_jobs = 0
    next_reconcile = 0.0

    while not shutdown.requested:
        now = time.monotonic()
        if now >= next_reconcile:
            open_jobs = reconcile(api, k8s, selector).open_jobs
            next_reconcile = now + settings.reconcile_seconds

        if open_jobs >= settings.max_open_jobs:
            log.info(
                "back-pressure: %d open jobs >= %d, not popping",
                open_jobs,
                settings.max_open_jobs,
            )
            shutdown.sleep(settings.backpressure_seconds)
            open_jobs = count_open_jobs(k8s.list_jobs(selector))
            continue

        work_id = workqueue.pop_work_id(
            redis_db, worker.queue_name, settings.pop_timeout
        )
        if work_id is None:
            continue
        if dispatch_one(work_id, api, k8s, own_pod, worker, settings):
            open_jobs += 1

    log.info("dispatcher stopping")


def label_selector(priority: str) -> str:
    return (
        f"app.kubernetes.io/name={jobspec.APP_NAME},{jobspec.PRIORITY_LABEL}={priority}"
    )


def dispatch_one(
    work_id_raw: str,
    api: PosdaApi,
    k8s: KubernetesClient,
    own_pod: dict,
    worker: WorkerSettings,
    settings: DispatchSettings,
) -> bool:
    """Create the Job for one popped id; True if a Job now exists for it."""
    try:
        work_id = int(work_id_raw)
    except ValueError:
        log.error("ignoring non-numeric queue item %r", work_id_raw)
        return False

    manifest = jobspec.build_job_manifest(
        own_pod, work_id, worker.worker_priority, settings
    )
    try:
        k8s.create_job(manifest)
    except JobAlreadyExists:
        log.warning(
            "job %s already exists, not re-dispatching", manifest["metadata"]["name"]
        )
        return True
    except (KubernetesApiError, requests.RequestException) as exc:
        log.exception("could not create job for work item %s", work_id)
        report_dispatch_error(api, work_id, str(exc))
        return False

    log.info("dispatched work item %s as job %s", work_id, manifest["metadata"]["name"])
    return True


def report_dispatch_error(api: PosdaApi, work_id: int, reason: str) -> None:
    """Mark the row errored so a popped item is never silently lost.

    Unlike the legacy loop, a failure here is logged and swallowed: one bad
    item must not crash-loop the dispatcher for every item behind it.
    """
    try:
        api.set_status_errored(work_id, None, None, {"dispatch_error": reason})
    except Exception:
        log.exception("could not report work item %s as errored", work_id)


def reconcile(api: PosdaApi, k8s: KubernetesClient, selector: str) -> ReconcileResult:
    """Mark the rows of failed Jobs errored; return how many Jobs are still open."""
    jobs = k8s.list_jobs(selector)
    result = ReconcileResult(open_jobs=count_open_jobs(jobs))
    for job in jobs:
        if not is_failed(job):
            continue
        try:
            if reconcile_failed_job(api, k8s, job):
                result.errored_work_ids.append(work_id_of(job))
        except Exception:
            log.exception("could not reconcile job %s", job["metadata"]["name"])
    return result


def reconcile_failed_job(api: PosdaApi, k8s: KubernetesClient, job: dict) -> bool:
    work_id = work_id_of(job)
    if not work_is_open(api.get_work_item(work_id)):
        return False
    mark_failed_job_errored(api, k8s, job)
    return True


def work_id_of(job: dict) -> int:
    return int(job["metadata"]["labels"][jobspec.WORK_ID_LABEL])


def work_is_open(work_item: dict) -> bool:
    return not work_item.get("finished") and not work_item.get("failed")


def mark_failed_job_errored(api: PosdaApi, k8s: KubernetesClient, job: dict) -> None:
    name = job["metadata"]["name"]
    work_id = work_id_of(job)
    metrics = pod_termination_metrics(k8s, name, job)
    log.warning(
        "job %s failed without reporting; marking work %s errored: %s",
        name,
        work_id,
        metrics,
    )
    api.set_status_errored(work_id, None, None, metrics)


def _condition(job: dict, condition_type: str) -> dict | None:
    for condition in job.get("status", {}).get("conditions", []):
        if (
            condition.get("type") == condition_type
            and condition.get("status") == "True"
        ):
            return condition
    return None


def is_failed(job: dict) -> bool:
    return _condition(job, "Failed") is not None


def is_finished(job: dict) -> bool:
    return is_failed(job) or _condition(job, "Complete") is not None


def count_open_jobs(jobs: list[dict]) -> int:
    return sum(1 for job in jobs if not is_finished(job))


def pod_termination_metrics(k8s: KubernetesClient, job_name: str, job: dict) -> dict:
    """What went wrong, from the Job condition and the newest pod if it still exists."""
    metrics: dict = {"k8s_job": job_name}
    failure = _condition(job, "Failed") or {}
    _put(metrics, "job_failure_reason", failure.get("reason"))
    _put(metrics, "job_failure_message", failure.get("message"))

    pod = newest_pod(k8s.list_pods(f"job-name={job_name}"))
    if pod is None:
        return metrics
    status = pod.get("status", {})
    _put(metrics, "k8s_pod", pod["metadata"]["name"])
    _put(metrics, "pod_phase", status.get("phase"))
    _put(metrics, "pod_reason", status.get("reason"))

    terminated = container_termination(status)
    _put(metrics, "termination_reason", terminated.get("reason"))
    _put(metrics, "exit_code", terminated.get("exitCode"))
    _put(metrics, "termination_message", terminated.get("message"))
    return metrics


def newest_pod(pods: list[dict]) -> dict | None:
    if not pods:
        return None
    return max(pods, key=lambda p: p["metadata"].get("creationTimestamp", ""))


def container_termination(pod_status: dict) -> dict:
    for cs in pod_status.get("containerStatuses", []):
        for state_key in ("state", "lastState"):
            terminated = cs.get(state_key, {}).get("terminated")
            if terminated:
                return terminated
    return {}


def _put(metrics: dict, key: str, value: object) -> None:
    if value is not None:
        metrics[key] = value
