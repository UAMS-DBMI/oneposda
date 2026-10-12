"""Build the Job manifest for one work item from the dispatcher's own pod.

The dispatcher Deployment carries the same envFrom, volumes and mounts the
old worker Deployments did. Cloning its pod spec, rather than keeping a
second copy of all that in a template, means a Job can never drift from the
dispatcher and kustomize's hashed ConfigMap/Secret names resolve themselves.

Everything here is a pure function of dicts, so it is testable without a
cluster.
"""

from __future__ import annotations

import copy
import logging

from posda.worker.settings import DispatchSettings

log = logging.getLogger(__name__)

JOB_NAME_PREFIX = "posda-work-"
APP_NAME = "posda-work"
WORK_ID_LABEL = "posda.io/work-id"
PRIORITY_LABEL = "posda.io/priority"
KUEUE_QUEUE_LABEL = "kueue.x-k8s.io/queue-name"
KUEUE_PRIORITY_LABEL = "kueue.x-k8s.io/priority-class"

#: Job pods run worker_start.sh directly rather than through docker-entrypoint:
#: the script, the shim and this package ship on the posda-deploy volume, the
#: entrypoint is baked into the image. Flip to args ["worker", "run", id] once
#: a rebuilt image is everywhere.
WORKER_SCRIPT = "/home/posda/posdatools/worker_start.sh"
WORKING_DIR = "/home/posda/posdatools"
SERVICE_ACCOUNT_MOUNT = "/var/run/secrets/kubernetes.io/serviceaccount"

#: Scheduling identity and the dispatcher's own ServiceAccount do not belong
#: to the Job. restartPolicy is overridden to Never below.
POD_SPEC_FIELDS_TO_DROP = (
    "nodeName",
    "hostname",
    "subdomain",
    "serviceAccountName",
    "serviceAccount",
    "restartPolicy",
    "ephemeralContainers",
)
CONTAINER_FIELDS_TO_DROP = (
    "livenessProbe",
    "readinessProbe",
    "startupProbe",
    "lifecycle",
)


def job_name(work_id: int) -> str:
    return f"{JOB_NAME_PREFIX}{work_id}"


def pod_labels(work_id: int, priority: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": APP_NAME,
        "app.kubernetes.io/part-of": "posda",
        WORK_ID_LABEL: str(work_id),
        PRIORITY_LABEL: priority,
    }


def job_labels(work_id: int, priority: str, settings: DispatchSettings) -> dict:
    # The Kueue labels go on the Job only; Kueue manages the Job, not its pods.
    labels = {KUEUE_QUEUE_LABEL: settings.kueue_queue}
    if settings.kueue_priority_class:
        labels[KUEUE_PRIORITY_LABEL] = settings.kueue_priority_class
    labels.update(pod_labels(work_id, priority))
    return labels


def build_job_manifest(
    own_pod: dict, work_id: int, priority: str, settings: DispatchSettings
) -> dict:
    spec = clone_pod_spec(own_pod["spec"])
    container = worker_container(spec)
    spec["containers"] = [job_container(container, work_id, settings)]
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name(work_id),
            "namespace": settings.namespace,
            "labels": job_labels(work_id, priority, settings),
        },
        "spec": {
            "parallelism": 1,
            "completions": 1,
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": settings.ttl_seconds_after_finished,
            "template": {
                "metadata": {"labels": pod_labels(work_id, priority)},
                "spec": spec,
            },
        },
    }


def clone_pod_spec(pod_spec: dict) -> dict:
    spec = copy.deepcopy(pod_spec)
    for field in POD_SPEC_FIELDS_TO_DROP:
        spec.pop(field, None)
    strip_service_account_volumes(spec)
    spec["restartPolicy"] = "Never"
    # Job pods only talk to the Posda API; also stops kubelet re-injecting a
    # token volume under a new random name.
    spec["automountServiceAccountToken"] = False
    return spec


def strip_service_account_volumes(spec: dict) -> None:
    """Remove the admission-injected ``kube-api-access-*`` volume and mounts."""
    injected = {
        volume["name"]
        for volume in spec.get("volumes", [])
        if volume["name"].startswith("kube-api-access-")
    }
    if not injected:
        return
    spec["volumes"] = [v for v in spec["volumes"] if v["name"] not in injected]
    for container in spec.get("containers", []) + spec.get("initContainers", []):
        container["volumeMounts"] = [
            m for m in container.get("volumeMounts", []) if m["name"] not in injected
        ]


def worker_container(spec: dict) -> dict:
    containers = spec.get("containers", [])
    if len(containers) != 1:
        raise ValueError(
            f"expected exactly one container in the dispatcher pod, "
            f"found {len(containers)}; sidecars would be cloned into every Job"
        )
    return containers[0]


def job_container(container: dict, work_id: int, settings: DispatchSettings) -> dict:
    result = copy.deepcopy(container)
    for field in CONTAINER_FIELDS_TO_DROP:
        result.pop(field, None)
    result["command"] = [WORKER_SCRIPT]
    result["args"] = ["run", str(work_id)]
    result["workingDir"] = WORKING_DIR
    result["resources"] = job_resources(container.get("resources", {}), settings)
    return result


def job_resources(own: dict, settings: DispatchSettings) -> dict:
    """Resource block for the Job container: env overrides, else the dispatcher's.

    Kueue meters requests, so an unrequested Job is admitted for free; warn
    rather than fail if that is what the configuration amounts to.
    """
    own_requests = own.get("requests", {})
    own_limits = own.get("limits", {})
    requests = _drop_none(
        {
            "cpu": settings.cpu_request or own_requests.get("cpu"),
            "memory": settings.memory_request or own_requests.get("memory"),
        }
    )
    limits = _drop_none(
        {
            "cpu": settings.cpu_limit or own_limits.get("cpu"),
            "memory": settings.memory_limit or own_limits.get("memory"),
        }
    )
    for resource in ("cpu", "memory"):
        if resource not in requests:
            log.warning(
                "no %s request for Job pods: set POSDA_JOB_%s_REQUEST, "
                "or Kueue will not meter it",
                resource,
                resource.upper(),
            )
    resources: dict = {}
    if requests:
        resources["requests"] = requests
    if limits:
        resources["limits"] = limits
    return resources


def _drop_none(mapping: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in mapping.items() if value is not None}
