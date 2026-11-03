"""Run against an emulator, never a real bucket:

    docker run -d -p 4443:4443 fsouza/fake-gcs-server -scheme http -public-host localhost:4443
    STORAGE_EMULATOR_HOST=http://localhost:4443 pytest test_idc_bucket.py
"""
import json
import os
import uuid

import pytest

if not os.getenv("STORAGE_EMULATOR_HOST"):
    pytest.skip("STORAGE_EMULATOR_HOST not set", allow_module_level=True)

from papi.util import idc_bucket as bucket  # noqa: E402

NO_BACKOFF = 0.001


@pytest.fixture
def base_url():
    client = bucket._storage_client()
    if not client.bucket("idc-bucket-test").exists():
        client.create_bucket("idc-bucket-test")
    return f"gs://idc-bucket-test/{uuid.uuid4().hex}/v1"


def lock_holder(base_url):
    return bucket._blob(base_url, bucket.LOCK_OBJECT).download_as_text()


def write_status(base_url, status):
    bucket._blob(base_url, bucket.STATUS_OBJECT).upload_from_string(
        json.dumps({"status": status})
    )


def test_second_worker_cannot_acquire(base_url):
    bucket.acquire_lock(base_url, "a", NO_BACKOFF)
    with pytest.raises(bucket.LockBusy):
        bucket.acquire_lock(base_url, "b", NO_BACKOFF)


def test_non_owner_cannot_release(base_url):
    bucket.acquire_lock(base_url, "a", NO_BACKOFF)
    assert bucket.release_lock(base_url, "b") is False
    assert lock_holder(base_url) == "Locked by a"


def test_acquire_after_release(base_url):
    bucket.acquire_lock(base_url, "a", NO_BACKOFF)
    assert bucket.release_lock(base_url, "a") is True
    bucket.acquire_lock(base_url, "b", NO_BACKOFF)


def test_lock_is_not_reentrant(base_url):
    bucket.acquire_lock(base_url, "a", NO_BACKOFF)
    with pytest.raises(bucket.LockBusy):
        bucket.acquire_lock(base_url, "a", NO_BACKOFF)


def test_release_after_forced_takeover_fails(base_url):
    bucket.acquire_lock(base_url, "a", NO_BACKOFF)
    bucket._blob(base_url, bucket.LOCK_OBJECT).delete()
    bucket.acquire_lock(base_url, "c", NO_BACKOFF)
    assert bucket.release_lock(base_url, "a") is False
    assert lock_holder(base_url) == "Locked by c"


def test_read_status_of_empty_folder(base_url):
    assert bucket.read_status(base_url) == ""


@pytest.mark.parametrize("status", [None, bucket.STATUS_DRAFT])
def test_set_ready(base_url, status):
    if status:
        write_status(base_url, status)
    bucket.set_ready(base_url, "t1", NO_BACKOFF)
    assert bucket.read_status(base_url) == bucket.STATUS_READY
    assert bucket.release_lock(base_url, "t1") is False  # already released


@pytest.mark.parametrize(
    "status",
    [
        bucket.STATUS_READY,
        bucket.STATUS_PROCESSING,
        bucket.STATUS_PROCESSED,
        bucket.STATUS_ERRORED,
        "ready to process",
    ],
)
def test_set_ready_refused(base_url, status):
    write_status(base_url, status)
    with pytest.raises(bucket.StatusConflict):
        bucket.set_ready(base_url, "t1", NO_BACKOFF)
    assert bucket.read_status(base_url) == status
    assert bucket.release_lock(base_url, "t1") is False  # refusal released it


def test_set_ready_waits_on_another_holder(base_url):
    bucket.acquire_lock(base_url, "posda-transfer-5", NO_BACKOFF)
    with pytest.raises(bucket.LockBusy):
        bucket.set_ready(base_url, "t1", NO_BACKOFF)
    assert bucket.read_status(base_url) == ""
