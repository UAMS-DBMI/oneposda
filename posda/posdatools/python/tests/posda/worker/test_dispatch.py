import signal

import pytest
import requests

from fakes import FakeK8s, FakePosdaApi, FakeRedis, make_job, make_own_pod, make_pod
from posda.ingest.lifecycle import ShutdownFlag
from posda.worker import dispatch
from posda.worker.k8s import KubernetesApiError
from posda.worker.settings import DispatchSettings, WorkerSettings

WORKER = WorkerSettings("http://web/papi", "redis", "1", "dispatcher-high-abc12", "tok")
SELECTOR = "app.kubernetes.io/name=posda-work,posda.io/priority=1"


def make_settings(**overrides):
    base = dict(
        pod_name="dispatcher-high-abc12",
        namespace="posda",
        kueue_queue="posda",
        kueue_priority_class=None,
        max_open_jobs=100,
        reconcile_seconds=60,
        backpressure_seconds=0,
        ttl_seconds_after_finished=3600,
        cpu_request="1",
        cpu_limit=None,
        memory_request="8Gi",
        memory_limit="8Gi",
    )
    base.update(overrides)
    return DispatchSettings(**base)


def stop(flag):
    return lambda *args: flag._request(signal.SIGTERM, None)


def run_loop(redis_db, api, k8s, settings, flag):
    dispatch.dispatch_loop(redis_db, api, k8s, make_own_pod(), WORKER, settings, flag)


def test_label_selector():
    assert dispatch.label_selector("1") == SELECTOR


class TestJobStatus:
    def test_conditions(self):
        assert dispatch.is_failed(make_job(1, condition="Failed"))
        assert not dispatch.is_failed(make_job(1, condition="Complete"))
        assert dispatch.is_finished(make_job(1, condition="Complete"))
        assert not dispatch.is_finished(make_job(1, active=1))
        assert not dispatch.is_finished(
            make_job(1)
        )  # suspended by Kueue, no conditions

    def test_count_open_jobs(self):
        jobs = [
            make_job(1, condition="Complete"),
            make_job(2, condition="Failed"),
            make_job(3, active=1),
            make_job(4),
        ]
        assert dispatch.count_open_jobs(jobs) == 2


class TestDispatchOne:
    def test_creates_a_job(self):
        api, k8s = FakePosdaApi(), FakeK8s()
        assert dispatch.dispatch_one(
            "7", api, k8s, make_own_pod(), WORKER, make_settings()
        )
        assert [j["metadata"]["name"] for j in k8s.created] == ["posda-work-7"]
        assert api.statuses == []

    def test_existing_job_is_not_redispatched(self, caplog):
        api, k8s = FakePosdaApi(), FakeK8s(jobs=[make_job(7)])
        assert dispatch.dispatch_one(
            "7", api, k8s, make_own_pod(), WORKER, make_settings()
        )
        assert k8s.created == [] and api.statuses == []
        assert "already exists" in caplog.text

    @pytest.mark.parametrize(
        "error",
        [
            KubernetesApiError(500, "boom", "POST", "/jobs"),
            requests.ConnectionError("down"),
        ],
    )
    def test_create_failure_marks_the_item_errored(self, error):
        api, k8s = FakePosdaApi(work_items={7: {}}), FakeK8s()
        k8s.create_error = error
        assert not dispatch.dispatch_one(
            "7", api, k8s, make_own_pod(), WORKER, make_settings()
        )
        status, work_id, _, _, metrics = api.statuses[0]
        assert (status, work_id) == ("errored", 7)
        assert "dispatch_error" in metrics

    def test_unreportable_create_failure_does_not_raise(self, caplog):
        api, k8s = FakePosdaApi(), FakeK8s()
        api.fail_status = True
        k8s.create_error = KubernetesApiError(500, "boom", "POST", "/jobs")
        assert not dispatch.dispatch_one(
            "7", api, k8s, make_own_pod(), WORKER, make_settings()
        )
        assert "could not report work item 7" in caplog.text

    def test_non_numeric_item_is_skipped(self, caplog):
        api, k8s = FakePosdaApi(), FakeK8s()
        assert not dispatch.dispatch_one(
            "bogus", api, k8s, make_own_pod(), WORKER, make_settings()
        )
        assert k8s.created == [] and "non-numeric" in caplog.text


class TestReconcile:
    def test_failed_job_with_open_row_is_errored_with_pod_details(self):
        job = make_job(7, condition="Failed")
        pod = make_pod(
            "posda-work-7",
            terminated={"reason": "OOMKilled", "exitCode": 137},
            phase="Failed",
        )
        api = FakePosdaApi(
            work_items={7: {"running": True, "finished": False, "failed": False}}
        )
        k8s = FakeK8s(jobs=[job, make_job(8, active=1)], pods=[pod])

        result = dispatch.reconcile(api, k8s, SELECTOR)

        assert result.open_jobs == 1 and result.errored_work_ids == [7]
        status, work_id, _, _, metrics = api.statuses[0]
        assert (status, work_id) == ("errored", 7)
        assert (
            metrics["termination_reason"] == "OOMKilled" and metrics["exit_code"] == 137
        )
        assert (
            metrics["k8s_job"] == "posda-work-7"
            and metrics["k8s_pod"] == "posda-work-7-p0d"
        )
        assert metrics["job_failure_reason"] == "BackoffLimitExceeded"

    def test_failed_job_with_closed_row_is_left_alone(self):
        api = FakePosdaApi(
            work_items={7: {"running": False, "finished": False, "failed": True}}
        )
        k8s = FakeK8s(jobs=[make_job(7, condition="Failed")])
        result = dispatch.reconcile(api, k8s, SELECTOR)
        assert result.errored_work_ids == [] and api.statuses == []

    def test_failed_job_whose_pod_is_gone_reports_the_condition_only(self):
        api = FakePosdaApi(work_items={7: {"running": True}})
        k8s = FakeK8s(jobs=[make_job(7, condition="Failed")])
        dispatch.reconcile(api, k8s, SELECTOR)
        metrics = api.statuses[0][4]
        assert metrics == {
            "k8s_job": "posda-work-7",
            "job_failure_reason": "BackoffLimitExceeded",
            "job_failure_message": "Job has reached the specified backoff limit",
        }

    def test_complete_and_active_jobs_are_untouched(self):
        api = FakePosdaApi(work_items={1: {"running": True}, 2: {"running": True}})
        k8s = FakeK8s(jobs=[make_job(1, condition="Complete"), make_job(2, active=1)])
        assert dispatch.reconcile(api, k8s, SELECTOR).open_jobs == 1
        assert api.statuses == []

    def test_one_bad_job_does_not_abort_the_pass(self, caplog):
        api = FakePosdaApi(
            work_items={8: {"running": True}}
        )  # work 7 is unknown to the API
        k8s = FakeK8s(
            jobs=[make_job(7, condition="Failed"), make_job(8, condition="Failed")]
        )
        result = dispatch.reconcile(api, k8s, SELECTOR)
        assert result.errored_work_ids == [8]
        assert "could not reconcile job posda-work-7" in caplog.text

    def test_newest_pod_wins(self):
        pods = [
            make_pod(
                "j",
                terminated={"reason": "Error", "exitCode": 1},
                created="2026-01-01T00:00:00Z",
            ),
            make_pod(
                "j",
                terminated={"reason": "OOMKilled", "exitCode": 137},
                created="2026-01-02T00:00:00Z",
            ),
        ]
        assert (
            dispatch.newest_pod(pods)["status"]["containerStatuses"][0]["state"][
                "terminated"
            ]["reason"]
            == "OOMKilled"
        )


class TestLoop:
    def test_dispatches_until_sigterm(self):
        flag = ShutdownFlag()
        redis_db = FakeRedis(queues={"work_queue_1": ["8", "7"]})
        redis_db.on_pop = lambda: (
            None if redis_db.lists["work_queue_1"] else stop(flag)()
        )
        api, k8s = FakePosdaApi(), FakeK8s()

        run_loop(redis_db, api, k8s, make_settings(), flag)

        assert [j["metadata"]["name"] for j in k8s.created] == [
            "posda-work-7",
            "posda-work-8",
        ]
        assert k8s.list_jobs_calls == 1  # the startup reconcile, none since

    def test_back_pressure_never_pops(self):
        flag = ShutdownFlag()
        redis_db = FakeRedis(queues={"work_queue_1": ["7"]})
        k8s = FakeK8s(jobs=[make_job(1, active=1), make_job(2)])

        def release_after_two_lists(fake):
            if fake.list_jobs_calls == 3:
                stop(flag)()

        k8s.on_list_jobs = release_after_two_lists

        run_loop(redis_db, FakePosdaApi(), k8s, make_settings(max_open_jobs=2), flag)

        assert redis_db.pops == 0
        assert redis_db.lists["work_queue_1"] == ["7"]  # still Redis's, not ours

    def test_pops_again_once_jobs_drain(self):
        flag = ShutdownFlag()
        redis_db = FakeRedis(queues={"work_queue_1": ["7"]})
        redis_db.on_pop = stop(flag)  # one pop, then stop
        k8s = FakeK8s(jobs=[make_job(1, active=1)])

        def drain(fake):
            if fake.list_jobs_calls == 2:
                fake.jobs.clear()

        k8s.on_list_jobs = drain

        run_loop(redis_db, FakePosdaApi(), k8s, make_settings(max_open_jobs=1), flag)

        assert redis_db.pops == 1
        assert [j["metadata"]["name"] for j in k8s.created] == ["posda-work-7"]

    def test_startup_reconcile_cleans_up_after_a_restart(self):
        flag = ShutdownFlag()
        redis_db = FakeRedis()
        redis_db.on_pop = stop(flag)
        api = FakePosdaApi(work_items={3: {"running": True}})
        k8s = FakeK8s(jobs=[make_job(3, condition="Failed")])

        run_loop(redis_db, api, k8s, make_settings(), flag)

        assert api.statuses[0][:2] == ("errored", 3)
