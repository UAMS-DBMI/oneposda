"""A minimal in-cluster Kubernetes client built on ``requests``.

The dispatcher needs four calls: read its own pod, create a Job, list its
Jobs, list a Job's pods. That is not enough to justify the official client
and its dependency tree, so this talks to the API server directly with the
ServiceAccount token kubelet mounts into the pod.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

from posda.worker.settings import SERVICE_ACCOUNT_DIR, read_namespace

log = logging.getLogger(__name__)

DEFAULT_HOST = "https://kubernetes.default.svc"
REQUEST_TIMEOUT = 30.0
BODY_EXCERPT = 500


class KubernetesApiError(RuntimeError):
    def __init__(self, status_code: int, body: str, method: str, path: str) -> None:
        self.status_code = status_code
        self.body = body
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} -> {status_code}: {body[:BODY_EXCERPT]}")


class JobAlreadyExists(KubernetesApiError):
    """Creating a Job whose name is taken: a 409 Conflict."""


def in_cluster_host() -> str:
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT")
    if host and port:
        return f"https://{host}:{port}"
    return DEFAULT_HOST


class KubernetesClient:
    def __init__(
        self,
        host: str,
        token_path: Path,
        ca_path: Path | None,
        namespace: str,
        session: requests.Session | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.token_path = token_path
        self.ca_path = ca_path
        self.namespace = namespace
        self._session = session or requests.Session()

    @classmethod
    def in_cluster(
        cls, namespace: str | None = None, sa_dir: Path = SERVICE_ACCOUNT_DIR
    ) -> KubernetesClient:
        ca_path = sa_dir / "ca.crt"
        return cls(
            host=in_cluster_host(),
            token_path=sa_dir / "token",
            ca_path=ca_path if ca_path.exists() else None,
            namespace=namespace or read_namespace(sa_dir / "namespace"),
        )

    def get_pod(self, name: str) -> dict:
        return self._request("GET", self._pods_path(name))

    def create_job(self, manifest: dict) -> dict:
        try:
            return self._request("POST", self._jobs_path(), json=manifest)
        except KubernetesApiError as exc:
            if exc.status_code == 409:
                raise JobAlreadyExists(
                    exc.status_code, exc.body, exc.method, exc.path
                ) from exc
            raise

    def list_jobs(self, label_selector: str) -> list[dict]:
        result = self._request(
            "GET", self._jobs_path(), params={"labelSelector": label_selector}
        )
        return result.get("items", [])

    def list_pods(self, label_selector: str) -> list[dict]:
        result = self._request(
            "GET", self._pods_path(), params={"labelSelector": label_selector}
        )
        return result.get("items", [])

    def _jobs_path(self, name: str | None = None) -> str:
        path = f"/apis/batch/v1/namespaces/{self.namespace}/jobs"
        return f"{path}/{name}" if name else path

    def _pods_path(self, name: str | None = None) -> str:
        path = f"/api/v1/namespaces/{self.namespace}/pods"
        return f"{path}/{name}" if name else path

    def _token(self) -> str:
        # Re-read on every call: bound ServiceAccount tokens rotate and kubelet
        # rewrites the file in place.
        return self.token_path.read_text().strip()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        resp = self._session.request(
            method,
            f"{self.host}{path}",
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {self._token()}"},
            verify=str(self.ca_path) if self.ca_path else True,
            timeout=REQUEST_TIMEOUT,
        )
        if not 200 <= resp.status_code < 300:
            raise KubernetesApiError(resp.status_code, resp.text, method, path)
        return resp.json()
