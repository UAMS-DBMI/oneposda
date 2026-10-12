"""In-memory stand-ins for the worker's collaborators.

Imported as ``from fakes import ...`` (the test directories have no
``__init__.py``, matching tests/posda/ingest).
"""

from __future__ import annotations

import copy
from typing import Callable

from posda.worker.api import PosdaApiError
from posda.worker.k8s import JobAlreadyExists


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.content = text.encode()

    def json(self):
        return self._json


Handler = Callable[[str, str, dict], FakeResponse]


class FakeSession:
    """Just enough of requests.Session: records every call, answers via handler."""

    def __init__(self, handler: Handler):
        self.handler = handler
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)


class FakePosdaApi:
    """The PosdaApi surface backed by dicts, with a log of status changes."""

    def __init__(self, work_items=None, subprocesses=None, paths=None):
        self.work_items = {int(k): dict(v) for k, v in (work_items or {}).items()}
        self.subprocesses = dict(subprocesses or {})
        self.paths = dict(paths or {})
        self.uploads: list[bytes] = []
        self.statuses: list[tuple] = []
        self.running_calls: list[tuple] = []
        self.fail_upload = False
        self.fail_status = False

    def set_status_running(self, work_id, node_hostname):
        self.running_calls.append((int(work_id), node_hostname))
        item = self._item(work_id)
        item.update(running=True, status="running", node_hostname=node_hostname)

    def get_work_item(self, work_id):
        return dict(self._item(work_id))

    def get_subprocess_info(self, subprocess_invocation_id):
        try:
            return dict(self.subprocesses[subprocess_invocation_id])
        except KeyError:
            raise PosdaApiError(
                f"No such subprocess_invocation_id: {subprocess_invocation_id}"
            )

    def get_path_from_file_id(self, file_id):
        try:
            return self.paths[file_id]
        except KeyError:
            raise PosdaApiError(f"No such file_id: {file_id}")

    def upload_file(self, fp):
        if self.fail_upload:
            raise PosdaApiError("File upload failed")
        fp.seek(0)
        self.uploads.append(fp.read())
        return len(self.uploads)

    def set_status_finished(self, work_id, stderr_file_id, stdout_file_id, metrics):
        self._status("finished", work_id, stderr_file_id, stdout_file_id, metrics)

    def set_status_errored(self, work_id, stderr_file_id, stdout_file_id, metrics):
        self._status("errored", work_id, stderr_file_id, stdout_file_id, metrics)

    def _status(self, status, work_id, stderr_file_id, stdout_file_id, metrics):
        if self.fail_status:
            raise PosdaApiError(b"status update failed")
        self.statuses.append(
            (status, int(work_id), stderr_file_id, stdout_file_id, metrics)
        )
        item = self.work_items.setdefault(int(work_id), {})
        item.update(
            running=False,
            status=status,
            finished=status == "finished",
            failed=status == "errored",
        )

    def _item(self, work_id):
        try:
            return self.work_items[int(work_id)]
        except KeyError:
            raise PosdaApiError(f"No such work_id: {work_id}")


class FakeRedis:
    """``brpop`` returns queued items, then None, as the real client does on timeout."""

    def __init__(self, queues=None, values=None):
        self.lists = {k: list(v) for k, v in (queues or {}).items()}
        self.values = dict(values or {})
        self.on_pop = None
        self.pops = 0

    def brpop(self, keys, timeout=None):
        self.pops += 1
        if self.on_pop is not None:
            self.on_pop()
        items = self.lists.get(keys, [])
        if not items:
            return None
        return keys, items.pop()

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def get(self, key):
        return self.values.get(key)


class FakeK8s:
    def __init__(self, own_pod=None, jobs=(), pods=()):
        self.own_pod = own_pod
        self.jobs = list(jobs)
        self.pods = list(pods)
        self.created: list[dict] = []
        self.create_error: Exception | None = None
        self.on_list_jobs = None
        self.list_jobs_calls = 0

    def get_pod(self, name):
        return copy.deepcopy(self.own_pod)

    def create_job(self, manifest):
        if self.create_error is not None:
            raise self.create_error
        name = manifest["metadata"]["name"]
        existing = [j["metadata"]["name"] for j in self.jobs + self.created]
        if name in existing:
            raise JobAlreadyExists(409, "already exists", "POST", "/jobs")
        self.created.append(manifest)
        return manifest

    def list_jobs(self, label_selector):
        self.list_jobs_calls += 1
        if self.on_list_jobs is not None:
            self.on_list_jobs(self)
        return list(self.jobs)

    def list_pods(self, label_selector):
        key, _, value = label_selector.partition("=")
        return [
            p for p in self.pods if p["metadata"].get("labels", {}).get(key) == value
        ]


def make_own_pod():
    """A dispatcher pod as the API returns it, injected fields included."""
    return {
        "metadata": {"name": "dispatcher-high-abc12", "namespace": "posda"},
        "spec": {
            "nodeName": "node-7",
            "hostname": "dispatcher-high-abc12",
            "serviceAccountName": "posda-scheduler",
            "serviceAccount": "posda-scheduler",
            "restartPolicy": "Always",
            "dnsPolicy": "ClusterFirst",
            "schedulerName": "default-scheduler",
            "terminationGracePeriodSeconds": 30,
            "securityContext": {},
            "tolerations": [
                {"key": "node.kubernetes.io/not-ready", "effect": "NoExecute"}
            ],
            "containers": [
                {
                    "name": "worker",
                    "image": "tcia/posda:1.0.4",
                    "args": ["worker", "dispatch"],
                    "env": [
                        {"name": "POSDA_WORKER_PRIORITY", "value": "1"},
                        {
                            "name": "POD_NAME",
                            "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}},
                        },
                    ],
                    "envFrom": [
                        {"secretRef": {"name": "common-env-abc123"}},
                        {"configMapRef": {"name": "posda-env-def456"}},
                    ],
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"memory": "256Mi"},
                    },
                    "livenessProbe": {"exec": {"command": ["true"]}},
                    "volumeMounts": [
                        {"name": "nas-public", "mountPath": "/nas/public"},
                        {
                            "name": "posda-deploy",
                            "mountPath": "/home/posda/posdatools",
                            "subPath": "oneposda/posda/posdatools",
                            "readOnly": True,
                        },
                        {
                            "name": "kube-api-access-xyz99",
                            "mountPath": "/var/run/secrets/kubernetes.io/serviceaccount",
                            "readOnly": True,
                        },
                    ],
                }
            ],
            "volumes": [
                {
                    "name": "nas-public",
                    "persistentVolumeClaim": {"claimName": "nas-public"},
                },
                {
                    "name": "posda-deploy",
                    "persistentVolumeClaim": {"claimName": "posda-deploy-nfs40"},
                },
                {"name": "kube-api-access-xyz99", "projected": {"sources": []}},
            ],
        },
    }


def make_job(work_id, queue="work_queue_1", condition=None, active=0):
    """A Job as the API lists it; ``condition`` is "Complete", "Failed" or None."""
    status = {"active": active}
    if condition:
        status["conditions"] = [
            {
                "type": condition,
                "status": "True",
                "reason": "BackoffLimitExceeded" if condition == "Failed" else "",
                "message": "Job has reached the specified backoff limit",
            }
        ]
    return {
        "metadata": {
            "name": f"posda-work-{work_id}",
            "labels": {
                "app.kubernetes.io/name": "posda-work",
                "posda.io/work-id": str(work_id),
                "posda.io/queue": queue,
            },
        },
        "status": status,
    }


def make_pod(
    job_name,
    terminated=None,
    phase="Failed",
    reason=None,
    created="2026-10-12T00:00:00Z",
):
    status = {"phase": phase}
    if reason:
        status["reason"] = reason
    if terminated:
        status["containerStatuses"] = [
            {"name": "worker", "state": {"terminated": terminated}}
        ]
    return {
        "metadata": {
            "name": f"{job_name}-p0d",
            "labels": {"job-name": job_name},
            "creationTimestamp": created,
        },
        "status": status,
    }
