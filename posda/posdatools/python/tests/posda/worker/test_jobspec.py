import copy

import pytest

from fakes import make_own_pod
from posda.worker import jobspec
from posda.worker.settings import DispatchSettings


def make_settings(**overrides):
    base = dict(
        pod_name="dispatcher-high-abc12",
        namespace="posda",
        kueue_queue="posda",
        kueue_priority_class=None,
        max_open_jobs=100,
        reconcile_seconds=60,
        backpressure_seconds=5,
        ttl_seconds_after_finished=3600,
        cpu_request="1",
        cpu_limit=None,
        memory_request="8Gi",
        memory_limit="8Gi",
    )
    base.update(overrides)
    return DispatchSettings(**base)


@pytest.fixture
def manifest():
    return jobspec.build_job_manifest(make_own_pod(), 7, "1", make_settings())


def pod_spec(manifest):
    return manifest["spec"]["template"]["spec"]


def container(manifest):
    return pod_spec(manifest)["containers"][0]


def test_job_identity_and_labels(manifest):
    assert manifest["apiVersion"] == "batch/v1" and manifest["kind"] == "Job"
    assert manifest["metadata"]["name"] == "posda-work-7"
    assert manifest["metadata"]["namespace"] == "posda"
    assert manifest["metadata"]["labels"] == {
        "kueue.x-k8s.io/queue-name": "posda",
        "app.kubernetes.io/name": "posda-work",
        "app.kubernetes.io/part-of": "posda",
        "posda.io/work-id": "7",
        "posda.io/priority": "1",
    }
    # Kueue manages the Job, not its pods: no queue label on the template.
    assert (
        "kueue.x-k8s.io/queue-name"
        not in manifest["spec"]["template"]["metadata"]["labels"]
    )
    assert manifest["spec"]["template"]["metadata"]["labels"]["posda.io/work-id"] == "7"


def test_priority_class_label_only_when_configured():
    with_class = jobspec.build_job_manifest(
        make_own_pod(), 7, "1", make_settings(kueue_priority_class="posda-high")
    )
    assert (
        with_class["metadata"]["labels"]["kueue.x-k8s.io/priority-class"]
        == "posda-high"
    )


def test_job_spec_settings(manifest):
    spec = manifest["spec"]
    assert (spec["parallelism"], spec["completions"], spec["backoffLimit"]) == (1, 1, 0)
    assert spec["ttlSecondsAfterFinished"] == 3600
    assert "suspend" not in spec  # Kueue's webhook sets it


def test_scheduling_identity_and_service_account_are_dropped(manifest):
    spec = pod_spec(manifest)
    for field in ("nodeName", "hostname", "serviceAccountName", "serviceAccount"):
        assert field not in spec
    assert spec["restartPolicy"] == "Never"
    assert spec["automountServiceAccountToken"] is False
    assert [v["name"] for v in spec["volumes"]] == ["nas-public", "posda-deploy"]
    assert [m["name"] for m in container(manifest)["volumeMounts"]] == [
        "nas-public",
        "posda-deploy",
    ]


def test_everything_else_is_copied(manifest):
    own = make_own_pod()["spec"]
    spec = pod_spec(manifest)
    assert spec["tolerations"] == own["tolerations"]
    assert spec["dnsPolicy"] == own["dnsPolicy"]
    assert spec["terminationGracePeriodSeconds"] == 30
    c = container(manifest)
    assert c["image"] == "tcia/posda:1.0.4"
    assert c["env"] == own["containers"][0]["env"]
    assert c["envFrom"] == own["containers"][0]["envFrom"]
    assert "livenessProbe" not in c


def test_container_runs_the_worker_script_directly(manifest):
    c = container(manifest)
    assert c["command"] == ["/home/posda/posdatools/worker_start.sh"]
    assert c["args"] == ["run", "7"]
    assert c["workingDir"] == "/home/posda/posdatools"


def test_resources_from_env(manifest):
    assert container(manifest)["resources"] == {
        "requests": {"cpu": "1", "memory": "8Gi"},
        "limits": {"memory": "8Gi"},
    }


def test_resources_fall_back_to_the_dispatchers_own():
    settings = make_settings(cpu_request=None, memory_request=None, memory_limit=None)
    m = jobspec.build_job_manifest(make_own_pod(), 7, "1", settings)
    assert container(m)["resources"] == {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"memory": "256Mi"},
    }


def test_missing_requests_warn_and_omit_the_key(caplog):
    pod = make_own_pod()
    del pod["spec"]["containers"][0]["resources"]
    settings = make_settings(cpu_request=None, memory_request=None, memory_limit=None)
    m = jobspec.build_job_manifest(pod, 7, "1", settings)
    assert container(m)["resources"] == {}
    assert (
        "POSDA_JOB_CPU_REQUEST" in caplog.text
        and "POSDA_JOB_MEMORY_REQUEST" in caplog.text
    )


def test_two_containers_are_refused():
    pod = make_own_pod()
    pod["spec"]["containers"].append({"name": "sidecar", "image": "x"})
    with pytest.raises(ValueError, match="exactly one container"):
        jobspec.build_job_manifest(pod, 7, "1", make_settings())


def test_input_pod_is_not_mutated():
    pod = make_own_pod()
    before = copy.deepcopy(pod)
    jobspec.build_job_manifest(pod, 7, "1", make_settings())
    assert pod == before
