"""Environment-derived settings for the three worker modes.

``WorkerSettings`` is what every mode needs to talk to the Posda API (and, for
the legacy loop and the dispatcher, Redis). It is read through
``posda.config.Config`` with exactly the keys and defaults the original
WorkerNode.py used, so the warnings it logs for unset variables are unchanged.

``DispatchSettings`` only matters to the dispatcher. It is read straight from
``os.environ`` because ``Config.get`` warns on every missing variable and most
of these knobs are optional.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from posda.config import Config

SERVICE_ACCOUNT_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
SA_NAMESPACE_FILE = SERVICE_ACCOUNT_DIR / "namespace"


@dataclass(frozen=True)
class WorkerSettings:
    api_url: str | None
    redis_host: str
    worker_priority: str
    node_name: str
    api_token: str | None

    @property
    def queue_name(self) -> str:
        return f"work_queue_{self.worker_priority}"

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/v1"


@dataclass(frozen=True)
class DispatchSettings:
    pod_name: str
    namespace: str
    kueue_queue: str
    kueue_priority_class: str | None
    max_open_jobs: int
    reconcile_seconds: int
    backpressure_seconds: int
    ttl_seconds_after_finished: int
    cpu_request: str | None
    cpu_limit: str | None
    memory_request: str | None
    memory_limit: str | None
    pop_timeout: int = 5


def load_worker_settings() -> WorkerSettings:
    """Read the legacy variables, in the legacy order, with the legacy defaults."""
    return WorkerSettings(
        api_url=Config.get("internal-api-url"),
        redis_host=Config.get("redis-host", default="redis"),
        worker_priority=str(Config.get("worker-priority", default=0)),
        node_name=Config.get("worker-name", default=platform.node()),
        api_token=Config.get("api_system_token"),
    )


def require_api_url(settings: WorkerSettings) -> str:
    """The legacy loop only fails on its first request; the new modes fail early."""
    if not settings.api_url:
        raise RuntimeError("POSDA_INTERNAL_API_URL is not set")
    return settings.api_url


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)


def read_namespace(namespace_file: Path = SA_NAMESPACE_FILE) -> str:
    return namespace_file.read_text().strip()


def resolve_namespace(namespace_file: Path = SA_NAMESPACE_FILE) -> str:
    explicit = os.environ.get("POD_NAMESPACE")
    if explicit:
        return explicit
    return read_namespace(namespace_file)


def load_dispatch_settings() -> DispatchSettings:
    pod_name = os.environ.get("POD_NAME")
    if not pod_name:
        raise RuntimeError(
            "POD_NAME is not set; the dispatcher needs it (downward API) "
            "to read its own pod spec"
        )
    return DispatchSettings(
        pod_name=pod_name,
        namespace=resolve_namespace(),
        kueue_queue=os.environ.get("POSDA_KUEUE_QUEUE", "posda"),
        kueue_priority_class=os.environ.get("POSDA_KUEUE_PRIORITY_CLASS") or None,
        max_open_jobs=_env_int("POSDA_DISPATCH_MAX_OPEN_JOBS", 100),
        reconcile_seconds=_env_int("POSDA_DISPATCH_RECONCILE_SECONDS", 60),
        backpressure_seconds=_env_int("POSDA_DISPATCH_BACKPRESSURE_SECONDS", 5),
        ttl_seconds_after_finished=_env_int("POSDA_JOB_TTL_SECONDS", 3600),
        cpu_request=os.environ.get("POSDA_JOB_CPU_REQUEST") or None,
        cpu_limit=os.environ.get("POSDA_JOB_CPU_LIMIT") or None,
        memory_request=os.environ.get("POSDA_JOB_MEMORY_REQUEST") or None,
        memory_limit=os.environ.get("POSDA_JOB_MEMORY_LIMIT") or None,
    )
