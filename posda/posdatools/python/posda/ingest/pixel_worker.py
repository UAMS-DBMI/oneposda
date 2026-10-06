"""Port of ``FastPixelInfoWorker.pl``.

A second pass over each file that records where the pixel data lives.
Unlike the file worker it parses with no size limit -- ``Posda::Try`` rather
than ``Posda::NewTry`` -- because it needs the pixel bytes themselves to
digest them.

This pass exists because the first one cannot do the job: with
``skip_large => 256`` the pixel element has no value, so ImagePixel's dedup
tables are never populated. This worker fills in ``dicom_file``'s pixel
columns instead, which is why those are populated while
``unique_pixel_data`` is empty.
"""

from __future__ import annotations

import hashlib
import logging

from posda.ingest import parse
from posda.ingest.db import Database
from posda.ingest.values import raw_item
from posda.ingest.worker import FileJob

log = logging.getLogger(__name__)

PIXEL_DATA_TAG = 0x7FE00010


def populate_pixel_info(db: Database, job: FileJob) -> None:
    """Port of ``PopulateOneFile``."""
    # skip_large=0 mirrors Posda::Try, which applies no element size limit.
    result = parse.parse(job.path, skip_large=0)
    if not result.is_dicom:
        log.info("File (%s): %s didn't parse", job.file_id, job.path)
        return

    raw = raw_item(result.values.dataset, PIXEL_DATA_TAG, result.values.skip_large)
    value = getattr(raw, "value", None) if raw is not None else None
    if not isinstance(value, bytes):
        db.execute(
            "update dicom_file set has_pixel_data = false where file_id = %s",
            [job.file_id],
        )
        return

    db.execute(
        "update dicom_file set has_pixel_data = true, pixel_data_digest = %s,"
        " pixel_data_offset = %s, pixel_data_length = %s where file_id = %s",
        [
            hashlib.md5(value).hexdigest(),
            getattr(raw, "value_tell", None),
            len(value),
            job.file_id,
        ],
    )
