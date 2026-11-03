"""The API's side of the status.json handshake with IDC's ETL.

The transfer daemon holds this lock while it uploads (idc-transfer-daemon,
src/versionlock.go). The object names and status literals here must match it.
Everything here blocks, so async callers use asyncio.to_thread.
"""
import json
import logging
import os
import time
from typing import Optional, Tuple

STATUS_OBJECT = "status.json"
LOCK_OBJECT = "status.lock"

# Exact literals: IDC string-compares them.
STATUS_DRAFT = "Draft"
STATUS_READY = "Ready for processing"
STATUS_PROCESSING = "Processing"
STATUS_PROCESSED = "Processed"
STATUS_ERRORED = "Errored"

# An upload may overwrite these; anything else is closed. Same rule as the
# daemon's statusAllowsWrite. "" is a folder with no status file yet.
OVERWRITABLE_STATUSES = {"", STATUS_DRAFT, STATUS_READY, STATUS_ERRORED}

LOCK_RETRIES = 3
LOCK_BACKOFF_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 10

logger = logging.getLogger(__name__)


class BucketUnavailable(Exception):
    """The bucket could not be reached, or the API has no access to it."""


class LockBusy(Exception):
    """Someone else holds the version's lock."""


class StatusConflict(Exception):
    """The version's status doesn't allow what was asked."""


_client = None


def _storage_client():
    # Imported here so an image built before this dependency still starts: the
    # API's source is mounted, but its packages are baked into the image.
    global _client
    if _client is None:
        from google.cloud import storage

        key_json = os.getenv("GCS_KEY_JSON")
        key_file = os.getenv("GCS_KEY_FILE")
        if key_json:
            _client = storage.Client.from_service_account_info(json.loads(key_json))
        elif key_file:
            _client = storage.Client.from_service_account_json(key_file)
        else:
            _client = storage.Client()
    return _client


def _parse_base_url(base_url: str) -> Tuple[str, str]:
    if not base_url.startswith("gs://"):
        raise ValueError(f"not a gs:// URL: {base_url!r}")
    bucket, _, prefix = base_url[len("gs://"):].rstrip("/").partition("/")
    if not bucket or not prefix:
        raise ValueError(f"malformed gs:// URL: {base_url!r}")
    return bucket, prefix


def _blob(base_url: str, name: str):
    bucket, prefix = _parse_base_url(base_url)
    return _storage_client().bucket(bucket).blob(f"{prefix}/{name}")


def _lock_content(worker_id: str) -> str:
    return f"Locked by {worker_id}"


def acquire_lock(base_url: str, worker_id: str, backoff: float = LOCK_BACKOFF_SECONDS) -> None:
    """Atomic create-if-absent, with backoff. Not reentrant: a lock this worker
    already holds is still busy. Raises LockBusy when the retries run out."""
    from google.api_core.exceptions import PreconditionFailed

    blob = _blob(base_url, LOCK_OBJECT)
    for attempt in range(LOCK_RETRIES + 1):
        try:
            blob.upload_from_string(
                _lock_content(worker_id),
                content_type="text/plain",
                if_generation_match=0,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            return
        except PreconditionFailed:
            if attempt == LOCK_RETRIES:
                raise LockBusy(base_url) from None
            time.sleep(backoff * 2 ** attempt)


def release_lock(base_url: str, worker_id: str) -> bool:
    """Deletes the lock only if this worker holds it, conditioned on the
    generation that was read so a replaced lock survives. False if not held."""
    from google.api_core.exceptions import NotFound, PreconditionFailed

    blob = _blob(base_url, LOCK_OBJECT)
    try:
        holder = blob.download_as_text(timeout=REQUEST_TIMEOUT_SECONDS)
        if holder != _lock_content(worker_id):
            return False
        blob.delete(if_generation_match=blob.generation, timeout=REQUEST_TIMEOUT_SECONDS)
    except (NotFound, PreconditionFailed):
        return False
    return True


def read_status(base_url: str) -> str:
    """The version's status; "" when the folder has no status file."""
    from google.api_core.exceptions import NotFound

    try:
        text = _blob(base_url, STATUS_OBJECT).download_as_text(timeout=REQUEST_TIMEOUT_SECONDS)
    except NotFound:
        return ""
    return json.loads(text)["status"]


def _write_status(base_url: str, status: str) -> None:
    _blob(base_url, STATUS_OBJECT).upload_from_string(
        json.dumps({"status": status}),
        content_type="application/json",
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def set_ready(base_url: str, worker_id: str, backoff: float = LOCK_BACKOFF_SECONDS) -> None:
    """The curator's hand-off to IDC. Raises LockBusy, or StatusConflict unless
    the version is waiting on this step. Errored needs a re-push first: that's
    the fix, and it puts the version back at Draft."""
    acquire_lock(base_url, worker_id, backoff)
    try:
        status = read_status(base_url)
        if status not in ("", STATUS_DRAFT):
            raise StatusConflict(status)
        _write_status(base_url, STATUS_READY)
    finally:
        if not release_lock(base_url, worker_id):
            logger.error("IDC version lock was not ours to release: %s", base_url)


def status_or_unavailable(base_url: str) -> Tuple[Optional[str], Optional[str]]:
    """(status, None), or (None, reason) when it can't be read, for callers that
    report that rather than fail on it."""
    try:
        return read_status(base_url), None
    except Exception as e:
        logger.warning("Could not read IDC status for %s: %s", base_url, e)
        return None, f"{type(e).__name__}: {e}"
