import pytest

from posda.worker import settings

LEGACY_VARS = (
    "POSDA_INTERNAL_API_URL",
    "POSDA_REDIS_HOST",
    "POSDA_WORKER_PRIORITY",
    "POSDA_WORKER_NAME",
    "POSDA_API_SYSTEM_TOKEN",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in LEGACY_VARS + ("POSDA_WORKER_QUEUE", "POD_NAME", "POD_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    for name in list(__import__("os").environ):
        if (
            name.startswith("POSDA_JOB_")
            or name.startswith("POSDA_DISPATCH_")
            or name.startswith("POSDA_KUEUE_")
        ):
            monkeypatch.delenv(name)
    return monkeypatch


class TestWorkerSettings:
    def test_legacy_defaults(self, clean_env):
        s = settings.load_worker_settings()
        assert s.api_url is None
        assert s.redis_host == "redis"
        assert s.worker_priority == "0"
        assert s.queue_name == "work_queue_0"
        assert s.node_name  # platform.node()

    def test_reads_the_legacy_variables(self, clean_env):
        clean_env.setenv("POSDA_INTERNAL_API_URL", "http://web:8080/papi")
        clean_env.setenv("POSDA_WORKER_PRIORITY", "1")
        clean_env.setenv("POSDA_WORKER_NAME", "node-x")
        clean_env.setenv("POSDA_API_SYSTEM_TOKEN", "tok")
        s = settings.load_worker_settings()
        assert s.base_url == "http://web:8080/papi/v1"
        assert s.queue_name == "work_queue_1"
        assert s.node_name == "node-x"
        assert s.api_token == "tok"

    def test_queue_override_replaces_the_priority_queue(self, clean_env):
        clean_env.setenv("POSDA_WORKER_PRIORITY", "1")
        clean_env.setenv("POSDA_WORKER_QUEUE", "work_queue_kueue")
        s = settings.load_worker_settings()
        assert s.queue_name == "work_queue_kueue"
        assert s.worker_priority == "1"  # still read, still reported

    def test_empty_queue_override_is_ignored(self, clean_env):
        clean_env.setenv("POSDA_WORKER_QUEUE", "")
        assert settings.load_worker_settings().queue_name == "work_queue_0"

    def test_require_api_url(self, clean_env):
        with pytest.raises(RuntimeError, match="POSDA_INTERNAL_API_URL"):
            settings.require_api_url(settings.load_worker_settings())


class TestDispatchSettings:
    def test_pod_name_is_required(self, clean_env):
        with pytest.raises(RuntimeError, match="POD_NAME"):
            settings.load_dispatch_settings()

    def test_defaults(self, clean_env):
        clean_env.setenv("POD_NAME", "disp-1")
        clean_env.setenv("POD_NAMESPACE", "posda")
        s = settings.load_dispatch_settings()
        assert s.kueue_queue == "posda"
        assert s.kueue_priority_class is None
        assert s.max_open_jobs == 100
        assert s.reconcile_seconds == 60
        assert s.ttl_seconds_after_finished == 3600
        assert s.cpu_request is None
        assert s.pop_timeout == 5

    def test_overrides(self, clean_env):
        clean_env.setenv("POD_NAME", "disp-1")
        clean_env.setenv("POD_NAMESPACE", "posda-test")
        clean_env.setenv("POSDA_KUEUE_QUEUE", "other")
        clean_env.setenv("POSDA_KUEUE_PRIORITY_CLASS", "posda-high")
        clean_env.setenv("POSDA_DISPATCH_MAX_OPEN_JOBS", "7")
        clean_env.setenv("POSDA_JOB_MEMORY_LIMIT", "8Gi")
        s = settings.load_dispatch_settings()
        assert s.namespace == "posda-test"
        assert s.kueue_queue == "other"
        assert s.kueue_priority_class == "posda-high"
        assert s.max_open_jobs == 7
        assert s.memory_limit == "8Gi"

    def test_namespace_falls_back_to_the_service_account_file(
        self, clean_env, tmp_path
    ):
        ns_file = tmp_path / "namespace"
        ns_file.write_text("posda\n")
        assert settings.resolve_namespace(ns_file) == "posda"
