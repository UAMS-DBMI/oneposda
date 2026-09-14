"""Port of ``FastFileProcessWorker.pl``.

Pops a file off the Redis ``files`` list, parses it, writes ``file``,
``dicom_file`` and ``file_meta``, dispatches to the SOP-class handlers, then
forwards the same queue item to ``pixel_location`` for the pixel worker.

The queue payload is a two-element JSON array, ``[file_id, path]``, exactly
as the Perl encodes it, so Python and Perl workers can consume the same
queue during cutover.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from posda.ingest import fixes, iod, parse
from posda.ingest.db import Database
from posda.ingest.parse import ParseResult
from posda.ingest.sopclasses import sop_class_description

log = logging.getLogger(__name__)

DICOMDIR_SOP_CLASS = "1.2.840.10008.1.3.10"

_META_COLUMNS = (
    ("media_storage_sop_class", "(0002,0002)"),
    ("media_storage_sop_instance", "(0002,0003)"),
    ("xfer_syntax", "(0002,0010)"),
    ("imp_class_uid", "(0002,0012)"),
    ("imp_version_name", "(0002,0013)"),
    ("source_ae_title", "(0002,0016)"),
    ("private_info_uid", "(0002,0100)"),
    ("private_info", "(0002,0102)"),
)


@dataclass
class FileJob:
    file_id: int
    path: str

    @classmethod
    def from_json(cls, payload: str | bytes) -> "FileJob":
        file_id, path = json.loads(payload)
        return cls(file_id=file_id, path=path)

    def to_json(self) -> str:
        """Encode as the Perl does: a bare two-element array, no spaces.

        ``FastFileProcessDaemon.pl`` pushes ``encode_json($row_arrayref)``,
        so the payload is ``[123,"/path"]`` rather than an object.
        """
        return json.dumps([self.file_id, self.path], separators=(",", ":"))


def process_file(db: Database, job: FileJob) -> None:
    """Port of ``InsertOneFile``."""
    if not os.path.isfile(job.path):
        log.error("File (%s) not found", job.path)
        return

    db.execute(
        "update file_location set file_is_present = true where file_id = %s",
        [job.file_id],
    )

    result = parse.parse(job.path)
    if not result.is_dicom:
        # Note this also catches a Part 10 file whose dataset failed to
        # parse: that branch of the Perl never sets file_type, so the column
        # is left NULL rather than describing the file.
        log.info("import: Non DICOM (%s) (%s)", result.file_type, job.file_id)
        db.execute(
            "update file set is_dicom_file = false, file_type = %s"
            " where file_id = %s",
            [result.file_type, job.file_id],
        )
        return

    if fixes.ACTIVE.atomic_import:
        _import_dicom_atomic(db, job, result)
    else:
        _import_dicom(db, job, result)


def _import_dicom_atomic(db: Database, job: FileJob, result: ParseResult) -> None:
    """Import one file as a single transaction.

    On failure everything the file wrote is rolled back -- including the
    is_dicom_file update, which under autocommit is what strands a failed
    file partial and unqueued forever. A rolled-back file would then be
    re-queued by the daemon indefinitely, so a follow-up autocommit step
    records why it failed and clears ready_to_process to take it out of
    the replenish query. Re-queue a repaired file by setting
    ready_to_process back to true.
    """
    process_errors: list[str] = []
    try:
        with db.transaction():
            _import_dicom(db, job, result, process_errors)
    except Exception as exc:
        _record_rolled_back_import(db, job.file_id, process_errors, exc)
        raise


def _record_rolled_back_import(
    db: Database, file_id: int, process_errors: list[str], exc: Exception
) -> None:
    """Preserve the evidence a rollback would otherwise destroy."""
    for error in process_errors:
        db.execute(
            "insert into dicom_process_errors (file_id, error_msg)"
            " values (%s, %s)",
            [file_id, error],
        )
    db.execute(
        "insert into dicom_process_errors (file_id, error_msg) values (%s, %s)",
        [file_id, f"import failed, rows rolled back: {type(exc).__name__}: {exc}"],
    )
    db.execute(
        "update file set ready_to_process = false where file_id = %s",
        [file_id],
    )


def _import_dicom(
    db: Database,
    job: FileJob,
    result: ParseResult,
    process_errors: list[str] | None = None,
) -> None:
    errors: list[str] = []
    has_meta = False
    media_storage_sop_class = None

    if result.meta is not None:
        if result.meta.file_meta_version is not None:
            _insert_meta(db, job.file_id, result)
            has_meta = True
        else:
            errors.append("Meta header with no (0002,0001) (entry not created)")
        media_storage_sop_class = result.meta.get("(0002,0002)")

    is_dicom_dir = bool(has_meta and media_storage_sop_class == DICOMDIR_SOP_CLASS)
    dicom_file_type = "DICOMDIR" if is_dicom_dir else ""

    sop_class = result.values.get("(0008,0016)")
    has_sop_common = sop_class is not None
    if has_sop_common:
        dicom_file_type = sop_class_description(str(sop_class))

    db.execute(
        "update file set is_dicom_file = %s, file_type = 'parsed dicom file'"
        " where file_id = %s",
        [True, job.file_id],
    )
    db.execute(
        "insert into dicom_file"
        " (file_id, xfr_stx, has_meta, is_dicom_dir, has_sop_common,"
        "  dicom_file_type, dataset_digest)"
        " values (%s, %s, %s, %s, %s, %s, %s)",
        [
            job.file_id,
            # Posda::NewTry declares $xfr_stx and never assigns it, so this
            # column is unconditionally NULL. Confirmed against the dev
            # database: 0 of 1256 rows populated. Reproduced by default; see
            # posda.ingest.fixes.
            _transfer_syntax(result) if fixes.ACTIVE.xfr_stx else None,
            has_meta,
            is_dicom_dir,
            has_sop_common,
            dicom_file_type,
            result.digest,
        ],
    )
    for error in errors:
        db.execute(
            "insert into dicom_file_errors (file_id, error_msg) values (%s, %s)",
            [job.file_id, error],
        )

    if is_dicom_dir:
        # Posda::DB::DicomDir::Import is a stub that only prints.
        log.info("import: DicomDir (%s)", job.file_id)
    elif has_sop_common:
        log.info("import: DicomIod (%s)", job.file_id)
        iod.import_dataset(
            db,
            result.values,
            job.file_id,
            str(sop_class),
            dicom_file_type,
            errors=process_errors,
        )


def _transfer_syntax(result: ParseResult) -> str | None:
    """The transfer syntax UID from the file meta group, (0002,0010)."""
    if result.meta is None:
        return None
    value = result.meta.get("(0002,0010)")
    return None if value is None else str(value)


def _insert_meta(db: Database, file_id: int, result: ParseResult) -> None:
    meta = result.meta
    values = [
        file_id,
        meta.file_meta_version,
        meta.data_set_size,
        meta.data_set_start,
    ] + [meta.get(sig) for _, sig in _META_COLUMNS]
    columns = ", ".join(
        ["file_id", "file_meta", "data_set_size", "data_set_start"]
        + [column for column, _ in _META_COLUMNS]
    )
    placeholders = ", ".join(["%s"] * len(values))
    db.execute(f"insert into file_meta ({columns}) values ({placeholders})", values)
