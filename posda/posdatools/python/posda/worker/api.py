"""Client for the handful of Posda API endpoints the worker uses.

The error behaviour is a straight port of the original WorkerNode.py: every
unexpected status raises ``RuntimeError`` (``PosdaApiError`` is a subclass, so
callers that catch ``Exception`` or ``RuntimeError`` see no difference), and a
``[]`` body -- which the API returns with a 200 for an unknown id -- is turned
into the "No such ..." error the API should have sent.

The bearer token is never logged.
"""

from __future__ import annotations

import hashlib
import logging
from typing import BinaryIO

import requests

log = logging.getLogger(__name__)

WorkId = int | str


class PosdaApiError(RuntimeError):
    """A Posda API call did not succeed."""


class PosdaApi:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self._token = token
        self._session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}"

    def set_status_running(self, work_id: WorkId, node_hostname: str) -> None:
        url = self._url(f"worker/status/{work_id}/running")
        resp = self._session.post(
            url, json={"node_hostname": node_hostname}, headers=self._headers()
        )
        log.debug("POST %s -> %s", url, resp.status_code)
        if resp.status_code != 200:
            raise PosdaApiError(resp.content)
        log.debug("changed status to running: %s", work_id)

    def get_work_item(self, work_id: WorkId) -> dict:
        resp = self._session.get(
            self._url(f"worker/status/{work_id}"), headers=self._headers()
        )
        if resp.status_code != 200:
            log.error("Work item status returned: %s", resp.status_code)
            raise PosdaApiError(f"Work item status returned: {resp.status_code}")
        work_item = resp.json()
        if work_item == []:
            raise PosdaApiError(f"No such work_id: {work_id}")
        log.debug(work_item)
        return work_item

    def get_subprocess_info(self, subprocess_invocation_id: int) -> dict:
        resp = self._session.get(
            self._url(f"worker/subprocess/{subprocess_invocation_id}"),
            headers=self._headers(),
        )
        if resp.status_code != 200:
            log.error("Subprocess info returned: %s", resp.status_code)
            raise PosdaApiError(f"Subprocess info returned: {resp.status_code}")
        subp = resp.json()
        if subp == []:
            raise PosdaApiError(
                f"No such subprocess_invocation_id: {subprocess_invocation_id}"
            )
        log.debug(subp)
        return subp

    def get_path_from_file_id(self, file_id: int) -> str:
        resp = self._session.get(
            self._url(f"files/{file_id}/path"), headers=self._headers()
        )
        if resp.status_code != 200:
            log.error("Filepath returned: %s", resp.status_code)
            raise PosdaApiError(f"Filepath returned: {resp.status_code}")
        obj = resp.json()
        log.debug(obj)
        if obj == []:
            raise PosdaApiError(f"No such file_id: {file_id}")
        return obj["file_path"]

    def upload_file(self, fp: BinaryIO) -> int:
        digest = md5_of_file(fp)
        fp.seek(0)
        resp = self._session.put(
            self._url("import/file"),
            params={"digest": digest},
            data=fp,
            headers=self._headers(),
        )
        if resp.status_code != 200:
            log.error("File uploading failed: %s %s", resp.status_code, resp.text)
            raise PosdaApiError("File upload failed")
        return resp.json()["file_id"]

    def set_status_finished(
        self,
        work_id: WorkId,
        stderr_file_id: int | None,
        stdout_file_id: int | None,
        metrics: dict | None,
    ) -> None:
        self._set_status("finished", work_id, stderr_file_id, stdout_file_id, metrics)

    def set_status_errored(
        self,
        work_id: WorkId,
        stderr_file_id: int | None,
        stdout_file_id: int | None,
        metrics: dict | None,
    ) -> None:
        self._set_status("errored", work_id, stderr_file_id, stdout_file_id, metrics)

    def _set_status(
        self,
        status: str,
        work_id: WorkId,
        stderr_file_id: int | None,
        stdout_file_id: int | None,
        metrics: dict | None,
    ) -> None:
        # The server deletes both keys from the body unconditionally, so they
        # must always be present, even when None.
        body = dict(metrics or {})
        body.update(
            {"stderr_file_id": stderr_file_id, "stdout_file_id": stdout_file_id}
        )
        resp = self._session.post(
            self._url(f"worker/status/{work_id}/{status}"),
            json=body,
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise PosdaApiError(resp.content)


def md5_of_file(fp: BinaryIO) -> str:
    fp.seek(0)
    hash_md5 = hashlib.md5()
    for chunk in iter(lambda: fp.read(4096), b""):
        hash_md5.update(chunk)
    return hash_md5.hexdigest()
