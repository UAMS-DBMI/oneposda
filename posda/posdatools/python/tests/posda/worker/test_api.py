import io
import logging

import pytest

from fakes import FakeResponse, FakeSession
from posda.worker.api import PosdaApi, PosdaApiError, md5_of_file

TOKEN = "s3cret-token-value"


def make_api(handler):
    session = FakeSession(handler)
    return PosdaApi("http://web:8080/papi/v1", TOKEN, session=session), session


def ok(json_data=None):
    return lambda m, u, kw: FakeResponse(200, json_data)


class TestRequests:
    def test_set_status_running_posts_the_hostname(self):
        api, session = make_api(ok({}))
        api.set_status_running(5, "node-a")
        method, url, kw = session.calls[0]
        assert (method, url) == (
            "POST",
            "http://web:8080/papi/v1/worker/status/5/running",
        )
        assert kw["json"] == {"node_hostname": "node-a"}
        assert kw["headers"] == {"Authorization": f"Bearer {TOKEN}"}

    def test_get_work_item(self):
        api, session = make_api(ok({"work_id": 5, "subprocess_invocation_id": 9}))
        assert api.get_work_item(5)["subprocess_invocation_id"] == 9
        assert session.calls[0][1].endswith("/worker/status/5")

    def test_get_subprocess_info(self):
        api, session = make_api(ok({"command_line": "x"}))
        assert api.get_subprocess_info(9) == {"command_line": "x"}
        assert session.calls[0][1].endswith("/worker/subprocess/9")

    def test_get_path_from_file_id(self):
        api, session = make_api(ok({"file_path": "/nas/a"}))
        assert api.get_path_from_file_id(3) == "/nas/a"
        assert session.calls[0][1].endswith("/files/3/path")

    def test_upload_sends_digest_and_rewinds(self):
        api, session = make_api(ok({"file_id": 77}))
        fp = io.BytesIO(b"hello")
        fp.read()  # leave the offset at the end on purpose
        assert api.upload_file(fp) == 77
        method, url, kw = session.calls[0]
        assert (method, url) == ("PUT", "http://web:8080/papi/v1/import/file")
        assert kw["params"] == {"digest": md5_of_file(io.BytesIO(b"hello"))}
        assert kw["data"] is fp and fp.tell() == 0

    @pytest.mark.parametrize("status", ["finished", "errored"])
    def test_status_update_always_sends_both_file_ids(self, status):
        api, session = make_api(ok({}))
        getattr(api, f"set_status_{status}")(5, None, 12, {"Exit status": "0"})
        method, url, kw = session.calls[0]
        assert url.endswith(f"/worker/status/5/{status}")
        assert kw["json"] == {
            "Exit status": "0",
            "stderr_file_id": None,
            "stdout_file_id": 12,
        }

    def test_status_update_with_no_metrics(self):
        api, session = make_api(ok({}))
        api.set_status_errored(5, None, None, None)
        assert session.calls[0][2]["json"] == {
            "stderr_file_id": None,
            "stdout_file_id": None,
        }

    def test_metrics_dict_is_not_mutated(self):
        api, _ = make_api(ok({}))
        metrics = {"a": "1"}
        api.set_status_finished(1, 2, 3, metrics)
        assert metrics == {"a": "1"}


class TestErrors:
    def test_non_200_raises_runtime_error(self):
        api, _ = make_api(lambda m, u, kw: FakeResponse(500, text="boom"))
        with pytest.raises(RuntimeError, match="500"):
            api.get_work_item(1)
        with pytest.raises(RuntimeError, match="boom"):
            api.set_status_running(1, "n")
        with pytest.raises(RuntimeError):
            api.set_status_finished(1, None, None, None)
        with pytest.raises(PosdaApiError, match="upload failed"):
            api.upload_file(io.BytesIO(b"x"))

    @pytest.mark.parametrize(
        "call, message",
        [
            (lambda api: api.get_work_item(4), "No such work_id: 4"),
            (
                lambda api: api.get_subprocess_info(8),
                "No such subprocess_invocation_id: 8",
            ),
            (lambda api: api.get_path_from_file_id(2), "No such file_id: 2"),
        ],
    )
    def test_empty_list_means_not_found(self, call, message):
        api, _ = make_api(ok([]))
        with pytest.raises(PosdaApiError, match=message):
            call(api)


def test_token_never_reaches_the_log(caplog):
    caplog.set_level(logging.DEBUG)
    api, _ = make_api(ok({"file_id": 1, "file_path": "/p", "x": 1}))
    api.set_status_running(1, "n")
    api.get_work_item(1)
    api.get_subprocess_info(1)
    api.get_path_from_file_id(1)
    api.upload_file(io.BytesIO(b"x"))
    api.set_status_finished(1, 1, 1, {})
    assert TOKEN not in caplog.text
    assert caplog.text  # something was logged, so the check is meaningful
