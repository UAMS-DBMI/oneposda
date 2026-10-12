import pytest

from fakes import FakeResponse, FakeSession
from posda.worker import k8s


@pytest.fixture
def sa_dir(tmp_path):
    (tmp_path / "token").write_text("tok-1\n")
    (tmp_path / "ca.crt").write_text("CA")
    (tmp_path / "namespace").write_text("posda\n")
    return tmp_path


def make_client(sa_dir, handler, monkeypatch, namespace=None):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("KUBERNETES_SERVICE_PORT", raising=False)
    client = k8s.KubernetesClient.in_cluster(namespace, sa_dir=sa_dir)
    client._session = FakeSession(handler)
    return client


def test_in_cluster_reads_the_service_account_files(sa_dir, monkeypatch):
    client = make_client(sa_dir, lambda m, u, kw: FakeResponse(200, {}), monkeypatch)
    assert client.namespace == "posda"
    assert client.host == "https://kubernetes.default.svc"
    client.get_pod("p")
    method, url, kw = client._session.calls[0]
    assert (method, url) == (
        "GET",
        "https://kubernetes.default.svc/api/v1/namespaces/posda/pods/p",
    )
    assert kw["headers"] == {"Authorization": "Bearer tok-1"}
    assert kw["verify"] == str(sa_dir / "ca.crt")
    assert kw["timeout"] == k8s.REQUEST_TIMEOUT


def test_host_comes_from_the_service_env(sa_dir, monkeypatch):
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setenv("KUBERNETES_SERVICE_PORT", "6443")
    assert k8s.in_cluster_host() == "https://10.0.0.1:6443"


def test_token_is_reread_per_request(sa_dir, monkeypatch):
    client = make_client(sa_dir, lambda m, u, kw: FakeResponse(200, {}), monkeypatch)
    client.get_pod("p")
    (sa_dir / "token").write_text("tok-2")
    client.get_pod("p")
    tokens = [kw["headers"]["Authorization"] for _, _, kw in client._session.calls]
    assert tokens == ["Bearer tok-1", "Bearer tok-2"]


def test_create_job(sa_dir, monkeypatch):
    client = make_client(
        sa_dir,
        lambda m, u, kw: FakeResponse(201, kw["json"]),
        monkeypatch,
        "posda-test",
    )
    manifest = {"metadata": {"name": "j"}}
    assert client.create_job(manifest) == manifest
    method, url, kw = client._session.calls[0]
    assert (method, url) == (
        "POST",
        "https://kubernetes.default.svc/apis/batch/v1/namespaces/posda-test/jobs",
    )


def test_conflict_is_job_already_exists(sa_dir, monkeypatch):
    client = make_client(
        sa_dir, lambda m, u, kw: FakeResponse(409, text="exists"), monkeypatch
    )
    with pytest.raises(k8s.JobAlreadyExists) as exc:
        client.create_job({"metadata": {"name": "j"}})
    assert exc.value.status_code == 409


def test_other_errors_carry_status_and_body(sa_dir, monkeypatch):
    client = make_client(
        sa_dir, lambda m, u, kw: FakeResponse(500, text="kaboom"), monkeypatch
    )
    with pytest.raises(
        k8s.KubernetesApiError, match="POST .*jobs -> 500: kaboom"
    ) as exc:
        client.create_job({"metadata": {"name": "j"}})
    assert not isinstance(exc.value, k8s.JobAlreadyExists)


def test_list_jobs_and_pods_use_label_selectors(sa_dir, monkeypatch):
    client = make_client(
        sa_dir, lambda m, u, kw: FakeResponse(200, {"items": [{"a": 1}]}), monkeypatch
    )
    assert client.list_jobs("x=y") == [{"a": 1}]
    assert client.list_pods("job-name=j") == [{"a": 1}]
    (_, jobs_url, jobs_kw), (_, pods_url, pods_kw) = client._session.calls
    assert jobs_url.endswith("/namespaces/posda/jobs") and jobs_kw["params"] == {
        "labelSelector": "x=y"
    }
    assert pods_url.endswith("/namespaces/posda/pods") and pods_kw["params"] == {
        "labelSelector": "job-name=j"
    }
