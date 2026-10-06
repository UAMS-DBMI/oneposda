"""File identification and parsing, ported from ``Posda::NewTry``.

``Posda::NewTry->new`` does three things: hash the file, try to parse it as
Part 10 DICOM, and -- when that fails -- shell out to ``file(1)`` to describe
what it actually is. The ``file(1)`` output is stored verbatim in
``file.file_type`` ("diff output, ASCII text, with CRLF line terminators" and
friends are real values in the database), so this keeps shelling out rather
than substituting a libmagic binding, which would change those strings.

One ordering detail matters: ``NewTry`` sets ``skip_large => 256`` on the
parser *after* the file meta group has already been read, so the metaheader
is parsed without a size limit while the dataset is parsed with one.

``skip_large`` is also handed to ``dcmread`` as ``defer_size``. Posda's
parser seeks past large elements, so they never occupy memory; without
``defer_size`` pydicom reads every element -- pixel data included -- into
memory before the size limit is ever consulted, which is enough to OOM a
worker on large files. pydicom applies ``defer_size`` to the dataset only,
never to the file meta group, so the ordering above still holds.
"""

from __future__ import annotations

import hashlib
import logging
import re
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydicom import dcmread
from pydicom.errors import InvalidDicomError

from posda.ingest import fixes
from posda.ingest.values import SKIP_LARGE, ParsedValues

log = logging.getLogger(__name__)

# The offset of the dataset is the fixed Part 10 preamble (128) plus "DICM"
# (4) plus the explicit-VR UL element carrying the group length (12), plus
# the group length itself. Verified against Posda's DataSetStart.
_FIXED_META_PREFIX = 144

_FILE_OUTPUT_RE = re.compile(r"^(.*?): (.*)$")

STATUS_PARSED = "parsed dicom file"
STATUS_FAILED = "DICOM file - failed to parse"
STATUS_NOT_DICOM = "not dicom"


@dataclass
class MetaHeader:
    """The Part 10 file meta group, as Posda's parser exposes it."""

    values: ParsedValues
    data_set_start: int
    data_set_size: int

    @property
    def file_meta_version(self) -> int | None:
        """``(0002,0001)`` unpacked the way ``InsertMeta`` unpacks it.

        The element is OB; the Perl does ``unpack("v", ...)``, so the
        conventional ``\\x00\\x01`` becomes 256 rather than 1.
        """
        raw = self.values.dataset.get_item(0x00020001)
        value = getattr(raw, "value", None) if raw is not None else None
        if not isinstance(value, bytes) or len(value) < 2:
            return None
        return struct.unpack("<H", value[:2])[0]

    def get(self, sig: str) -> object:
        return self.values.get(sig)


@dataclass
class ParseResult:
    path: str
    digest: str
    length: int
    status: str
    values: ParsedValues | None = None
    meta: MetaHeader | None = None
    file_type: str | None = None
    errors: list[str] | None = None

    @property
    def is_dicom(self) -> bool:
        """Whether the worker should treat this as a parsed DICOM file.

        Mirrors ``exists $try->{dataset}``: a Part 10 file whose dataset
        fails to parse is *not* treated as DICOM, and because that branch
        never sets a file_type the column ends up NULL.
        """
        return self.values is not None


def digest_and_length(path: str | Path) -> tuple[str, int]:
    """MD5 and byte length of the whole file."""
    md5 = hashlib.md5()
    length = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            md5.update(chunk)
            length += len(chunk)
    return md5.hexdigest(), length


def parse(path: str | Path, skip_large: int | None = None) -> ParseResult:
    """Port of ``Posda::NewTry->new``.

    ``skip_large`` defaults to Posda's 256-byte limit, or to no limit when
    the load_large_values fix is enabled. Callers that need a specific limit
    (the pixel worker passes 0) still pass one explicitly.
    """
    if skip_large is None:
        skip_large = 0 if fixes.ACTIVE.load_large_values else SKIP_LARGE
    path = str(path)
    digest, length = digest_and_length(path)
    return parse_with_digest_and_length(path, digest, length, skip_large)


def parse_with_digest_and_length(
    path: str,
    digest: str,
    length: int,
    skip_large: int = SKIP_LARGE,
) -> ParseResult:
    try:
        dataset = dcmread(path, defer_size=_defer_size(skip_large))
    except InvalidDicomError:
        return _describe_non_dicom(path, digest, length)
    except Exception as exc:  # noqa: BLE001 - any read failure is "not Part 10"
        log.debug("dcmread failed for %s: %s", path, exc)
        return _describe_non_dicom(path, digest, length)

    if not getattr(dataset, "file_meta", None):
        # NewTry dies here rather than degrading; treat it as unparseable so
        # a single bad file cannot take the worker down.
        return ParseResult(
            path=path,
            digest=digest,
            length=length,
            status=STATUS_FAILED,
            errors=["No metaheader in default parser"],
        )

    meta = _meta_header(dataset, length)
    values = ParsedValues(dataset, skip_large=skip_large, source_path=path)
    return ParseResult(
        path=path,
        digest=digest,
        length=length,
        status=STATUS_PARSED,
        values=values,
        meta=meta,
        errors=values.errors,
    )


def _defer_size(skip_large: int) -> int | None:
    """The ``dcmread`` deferral threshold matching a ``skip_large`` limit.

    A deferred element keeps only its offset and length, which is all
    ``ParsedValues`` needs to treat it as skipped. With no limit (the pixel
    worker, or the load_large_values fix) every value has to be read.
    """
    return skip_large if skip_large else None


def _meta_header(dataset, length: int) -> MetaHeader:
    group_length = getattr(dataset.file_meta, "FileMetaInformationGroupLength", None)
    if group_length is None:
        data_set_start = 0
    else:
        data_set_start = _FIXED_META_PREFIX + int(group_length)
    return MetaHeader(
        # The file meta group is read before skip_large is applied.
        values=ParsedValues(dataset.file_meta, skip_large=0),
        data_set_start=data_set_start,
        data_set_size=length - data_set_start,
    )


def _describe_non_dicom(path: str, digest: str, length: int) -> ParseResult:
    return ParseResult(
        path=path,
        digest=digest,
        length=length,
        status=STATUS_NOT_DICOM,
        file_type=file_type(path),
    )


def file_type(path: str) -> str | None:
    """Describe a non-DICOM file with ``file(1)``.

    The raw description is what lands in ``file.file_type``, so the parsing
    matches the Perl's: take the first line and split on the first ": ".
    """
    try:
        completed = subprocess.run(
            ["file", path],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        log.warning("could not run file(1) on %s: %s", path, exc)
        return None
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    match = _FILE_OUTPUT_RE.match(first_line)
    return match.group(2) if match else None
