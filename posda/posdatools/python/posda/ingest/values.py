"""Posda::Parser value semantics, reproduced on top of pydicom.

The ingestion pipeline is being ported from Perl to Python bug-for-bug, so
this module deliberately reproduces Posda's behaviour rather than doing the
"correct" DICOM thing. Two differences from pydicom's defaults dominate
everything else and are the reason this module exists at all:

1. **Array-ness comes from the data dictionary, not the data.**
   ``Posda::Parser::DecodeElementValue`` returns a list whenever the
   dictionary VM is anything other than ``"1"`` -- even when the element
   holds a single value. pydicom returns a bare ``str``/``int``/``float``
   unless the *runtime* value has VM > 1. Handlers ported from
   ``Posda::DB::Modules`` branch on this: ``WindowLevel``, for example, does
   ``unless(ref($window_cntr) eq "ARRAY"){ return }``, so getting it wrong
   silently drops rows.

2. **Padding is stripped per Posda's own VR table**, which is not quite
   pydicom's. ``DA`` is stripped by pydicom but *not* by Posda, so a
   space-padded date survives into Posda's ``^(....)(..)(..)$`` check,
   fails it, and lands as NULL plus a "Bad date" row in
   ``dicom_process_errors``. Reproducing that requires the raw bytes, which
   is why every read here goes through ``Dataset.get_item`` rather than
   ``Dataset[tag].value``.

An audit of all 131 tags referenced by ``Posda::DB::{Modules,DicomIod}``
found zero disagreements between Posda's ``PubDataDict.pm`` VM/VR values and
pydicom's, so pydicom's dictionary is used as the VM source directly.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from pydicom.datadict import dictionary_VM, dictionary_VR
from pydicom.dataelem import RawDataElement
from pydicom.dataset import Dataset
from pydicom.filereader import read_deferred_data_element
from pydicom.sequence import Sequence

from posda.ingest.privatedict import private_vm_vr

# Posda::Parser is constructed with skip_large => 256 by Posda::NewTry, which
# is what the live fast-file-processor uses. Any non-SQ element longer than
# this is seek-skipped and never gets a value, so ExtractElementBySig returns
# undef for it and the corresponding column lands NULL.
SKIP_LARGE = 256


class DicomValueError(ValueError):
    """Raised for a malformed element signature or an undecodable value."""


@dataclass(frozen=True)
class VRDesc:
    """One row of Posda::DataDict's $VRDesc table."""

    type: str
    striptrailing: bool = False
    stripleading: bool = False
    padnull: bool = False


# Transcribed from Posda/include/Posda/DataDict.pm. Only the fields that
# unpad() and DecodeElementValue() actually consult are carried over.
VR_DESC: dict[str, VRDesc] = {
    "AE": VRDesc("text", striptrailing=True, stripleading=True),
    "AS": VRDesc("text"),
    "AT": VRDesc("ulong"),
    "CS": VRDesc("text", striptrailing=True, stripleading=True),
    "DA": VRDesc("text"),
    "DS": VRDesc("text", striptrailing=True, stripleading=True),
    "DT": VRDesc("text", striptrailing=True, stripleading=True),
    "FD": VRDesc("double"),
    "FL": VRDesc("float"),
    "IS": VRDesc("text", striptrailing=True, stripleading=True),
    "LO": VRDesc("text", striptrailing=True, stripleading=True),
    "LT": VRDesc("text", striptrailing=True),
    "OB": VRDesc("raw"),
    "OD": VRDesc("raw"),
    "OF": VRDesc("raw"),
    "OL": VRDesc("raw"),
    "OT": VRDesc("raw"),
    "OV": VRDesc("raw"),
    "OW": VRDesc("raw"),
    "PN": VRDesc("text", striptrailing=True),
    "SH": VRDesc("text", striptrailing=True, stripleading=True),
    "SL": VRDesc("slong"),
    "SQ": VRDesc("seq"),
    "SS": VRDesc("sshort"),
    "ST": VRDesc("text", striptrailing=True),
    "SV": VRDesc("sverylong"),
    "TM": VRDesc("text", striptrailing=True),
    "UC": VRDesc("text"),
    "UI": VRDesc("text", padnull=True),
    "UL": VRDesc("ulong"),
    "UN": VRDesc("raw"),
    "UR": VRDesc("text"),
    "US": VRDesc("ushort"),
    "UT": VRDesc("text"),
    "UV": VRDesc("uverylong"),
}

# Little-endian struct codes for Posda's numeric type categories. Posda
# decides endianness from the transfer syntax; every syntax the archive
# actually stores is little-endian, and Posda's own "vax" flag is set for all
# of them, so only the LE forms are reproduced here.
_NUMERIC_FORMATS: dict[str, tuple[str, int]] = {
    "ushort": ("<H", 2),
    "sshort": ("<h", 2),
    "ulong": ("<I", 4),
    "slong": ("<i", 4),
    "uverylong": ("<Q", 8),
    "sverylong": ("<q", 8),
    "float": ("<f", 4),
    "double": ("<d", 8),
}

_PUBLIC_SIG = re.compile(r"^\(([0-9a-fA-F]{4}),([0-9a-fA-F]{4})\)$")
_PRIVATE_SIG = re.compile(r'^\(([0-9a-fA-F]{4}),"([^"]*)",([0-9a-fA-F]{2})\)$')

# A signature with a trailing navigation expression, e.g.
# "(3006,0010)[0](3006,00c0)[1](3006,00c2)". The head may be a private
# element too: RTDvh reads (3005,"ITC_DVH_Computation",01) from inside a
# sequence item, so creators have to resolve at any depth, not just at the
# root.
_SIG_HEAD = re.compile(r"^\(([0-9a-fA-F]{4}),([0-9a-fA-F]{4})\)(.*)$")
_SIG_HEAD_PRIVATE = re.compile(r'^\(([0-9a-fA-F]{4}),"([^"]*)",([0-9a-fA-F]{2})\)(.*)$')
_INDEX_ONLY = re.compile(r"^\[(\d+)\]$")
_INDEX_THEN_REST = re.compile(r"^\[(\d+)\]>?(.*)$")

# One segment of a Substitutions pattern: a tag with either a literal index
# or a "<n>" wildcard.
_PATTERN_SEGMENT = re.compile(
    r"^\(([0-9a-fA-F]{4}),([0-9a-fA-F]{4})\)\[([^\]]+)\](.*)$"
)
_WILDCARD = re.compile(r"^<\d+>$")


@dataclass
class ParsedValues:
    """A dataset plus the running error list Posda threads through handlers."""

    dataset: Dataset
    errors: list[str] = field(default_factory=list)
    skip_large: int = SKIP_LARGE
    # Where the dataset was read from. The RT bridge re-parses the file in
    # Perl, so it needs the path rather than the in-memory dataset.
    source_path: str | None = None

    def get(self, sig: str) -> object:
        """Element read, equivalent to ``$ds->Get`` / ``ExtractElementBySig``.

        Handles public and private heads, plus the navigation suffixes the
        RT handlers use: ``[n]`` to index into a multi-valued element or a
        sequence, and ``[n]rest`` (or ``[n]>rest``) to descend into sequence
        item *n* and carry on.
        """
        return self._resolve(self.dataset, sig)

    def _resolve(self, dataset: Dataset, sig: str) -> object:
        tag, remain, declared = self._split_head(dataset, sig)
        if tag is None:
            return None
        if not remain:
            return self._read(dataset, tag, sig, declared)
        return self._navigate(dataset, tag, remain, sig, declared)

    def _split_head(
        self, dataset: Dataset, sig: str
    ) -> tuple[int | None, str, tuple[str, str] | None]:
        """Resolve the leading element of a signature to a tag.

        Returns ``(None, remain, None)`` when a private creator is absent,
        which Posda reports as an ordinary "no value" rather than an error.
        The third member carries the private dictionary's (VM, VR) when the
        head is a private element, since those are not in pydicom's
        dictionary and drive array-ness the same way public ones do.
        """
        match = _SIG_HEAD_PRIVATE.match(sig)
        if match is not None:
            group = int(match.group(1), 16)
            creator = match.group(2)
            offset = int(match.group(3), 16)
            if not group & 1:
                raise DicomValueError(f"only private groups have owner: {sig}")
            if dataset is None:
                return None, match.group(4), None
            try:
                block = dataset.private_block(group, creator)
            except KeyError:
                return None, match.group(4), None
            declared = private_vm_vr(creator, group, offset)
            return int(block.get_tag(offset)), match.group(4), declared

        match = _SIG_HEAD.match(sig)
        if match is None:
            raise DicomValueError(f"Sig ({sig}) didn't match")
        tag = (int(match.group(1), 16) << 16) | int(match.group(2), 16)
        return tag, match.group(3), None

    def _navigate(
        self,
        dataset: Dataset,
        tag: int,
        remain: str,
        sig: str,
        declared: tuple[str, str] | None = None,
    ) -> object:
        """Follow a navigation suffix, mirroring ExtractElementBySig."""
        if dataset is None or tag not in dataset:
            return None

        # A bare trailing [n] indexes whatever the value is -- Posda checks
        # this before it checks for SQ, so it serves both multi-valued
        # elements and sequences.
        match = _INDEX_ONLY.match(remain)
        if match is not None:
            value = self._value_for_navigation(dataset, tag, sig, declared)
            if not isinstance(value, (list, Sequence)):
                return None
            index = int(match.group(1))
            return value[index] if index < len(value) else None

        vr = _resolve_vr(dataset.get_item(tag, keep_deferred=True), tag, declared)
        if vr != "SQ":
            raise DicomValueError(
                f'invalid remaining ("{remain}") for non-seq ({vr}) element'
            )

        match = _INDEX_THEN_REST.match(remain)
        if match is None:
            raise DicomValueError(f'can\'t make sense of "{sig}"')
        index = int(match.group(1))
        rest = match.group(2)

        items = dataset[tag].value
        if not isinstance(items, (list, Sequence)) or index >= len(items):
            return None
        item = items[index]
        if not isinstance(item, Dataset):
            return None

        return self._resolve(item, rest)

    def _value_for_navigation(
        self,
        dataset: Dataset,
        tag: int,
        sig: str,
        declared: tuple[str, str] | None = None,
    ) -> object:
        """The value to index into for a trailing ``[n]``.

        Sequences have to come from ``dataset[tag].value`` -- pydicom's
        ``get_item`` hands back the undecoded bytes for SQ, which cannot be
        indexed by item.
        """
        vr = _resolve_vr(dataset.get_item(tag, keep_deferred=True), tag, declared)
        if vr == "SQ":
            return dataset[tag].value
        return self._read(dataset, tag, sig, declared)

    def substitutions(self, pattern: str) -> list[list[int]]:
        """Port of ``$ds->Substitutions($pat)``, returning its ``list``.

        The pattern is a chain of ``(gggg,eeee)[idx]`` segments ending in a
        bare tag. ``[<n>]`` is a wildcard that iterates every item of that
        sequence; the result is one list of item indices per match, in
        document order.

        Note the terminal element only has to *exist*: unlike a value read,
        a match is recorded even when the element was skipped for size.
        """
        matches: list[list[int]] = []
        self._substitute(self.dataset, pattern, [], matches)
        return matches

    def search(self, pattern: str) -> list[list[int]]:
        """Port of ``$ds->Search($pat)``.

        Semantically the same walk as :meth:`substitutions`, but forgiving
        where that one dies: a literal index naming something that is not a
        dataset, or a sequence whose value is not a list, simply ends that
        branch instead of raising.
        """
        matches: list[list[int]] = []
        self._substitute(self.dataset, pattern, [], matches, strict=False)
        return matches

    def _substitute(
        self,
        dataset: Dataset,
        pattern: str,
        accum: list[int],
        matches: list[list[int]],
        strict: bool = True,
    ) -> None:
        segment = _PATTERN_SEGMENT.match(pattern)
        if segment is not None:
            tag = (int(segment.group(1), 16) << 16) | int(segment.group(2), 16)
            index = segment.group(3)
            remain = segment.group(4)
            if dataset is None or tag not in dataset:
                return

            element = dataset[tag]
            if index.isdigit():
                if element.VR != "SQ":
                    raise DicomValueError("indexing a non seq VR")
                items = element.value
                position = int(index)
                if position >= len(items):
                    if strict:
                        raise DicomValueError("specified item of SQ is not a dataset")
                    return
                self._substitute(items[position], remain, accum, matches, strict)
                return

            if _WILDCARD.match(index) is None:
                raise DicomValueError("uncovered case")
            if element.VR != "SQ":
                raise DicomValueError("indexing a non seq VR")
            for position, item in enumerate(element.value):
                if item is None:
                    continue
                if not isinstance(item, Dataset):
                    raise DicomValueError("item in a SQ is not a dataset")
                if remain:
                    self._substitute(item, remain, accum + [position], matches, strict)
                else:
                    matches.append(accum + [position])
            return

        terminal = _PUBLIC_SIG.match(pattern)
        if terminal is None:
            raise DicomValueError(f"bad pattern: {pattern}")
        tag = (int(terminal.group(1), 16) << 16) | int(terminal.group(2), 16)
        if dataset is not None and tag in dataset:
            matches.append(accum)

    def get_private(self, sig: str) -> object:
        """Private-tag read. Retained as a name; get() handles both forms."""
        if _SIG_HEAD_PRIVATE.match(sig) is None:
            raise DicomValueError(f"Sig ({sig}) didn't match")
        return self.get(sig)

    def _read(
        self,
        dataset: Dataset,
        tag: int,
        sig: str,
        declared: tuple[str, str] | None = None,
    ) -> object:
        raw = raw_item(dataset, tag, self.skip_large, declared)
        if raw is None:
            return None
        vr = _resolve_vr(raw, tag, declared)
        if vr is None:
            return None
        if _is_skipped(raw, vr, self.skip_large):
            return None
        value = raw.value
        if value is None and isinstance(raw, RawDataElement):
            # A zero-length element in an implicit-VR file: pydicom stores
            # its raw value as None because the VR is unknown at read time.
            # Decode from the empty byte string Posda's parser saw, so
            # implicit and explicit files produce identical values and no
            # pydicom type reaches the database driver. (A deferred element
            # also has value None, but raw_item has already read it back or
            # _is_skipped has already returned.)
            value = b""
        elif not isinstance(value, bytes):
            # Genuinely converted element -- an undefined-length SQ, which
            # dcmread parses eagerly.
            return value
        vm = declared[0] if declared is not None else _dictionary_vm(tag)
        return decode_value(value, vr, vm, sig, self.errors)


def _perl_float(value: float) -> str:
    """Render a float the way Perl's default stringification does."""
    return f"{value:.15g}"


def _dictionary_vm(tag: int) -> str:
    try:
        return dictionary_VM(tag)
    except KeyError:
        # Posda falls back to treating unknown tags as multi-valued.
        return "1-n"


def _resolve_vr(
    raw: object, tag: int, declared: tuple[str, str] | None = None
) -> str | None:
    """The VR to decode ``raw`` with.

    An explicit VR of ``UN`` is treated exactly like an implicit-VR element
    with no VR at all: the dictionary decides. Public tags resolve through
    pydicom's dictionary; a private tag resolves through ``declared``, the
    (VM, VR) Posda's private dictionary carries for it. This matches
    Posda::Parser, which recasts a ``UN`` element to the dictionary VR
    (public or private) and only ever recasts ``UN`` -- an explicit VR that
    is merely *different* from the dictionary's is kept as written.
    Without a dictionary entry the raw ``UN`` (or None) stands.
    """
    vr = getattr(raw, "VR", None)
    if vr not in (None, "UN", ""):
        return str(vr)
    try:
        return dictionary_VR(tag)
    except KeyError:
        pass
    if declared is not None:
        return declared[1]
    return vr if vr else None


def raw_item(
    dataset: Dataset,
    tag: int,
    skip_large: int,
    declared: tuple[str, str] | None = None,
) -> object:
    """``Dataset.get_item`` honouring the deferred reads ``parse`` sets up.

    ``parse`` passes ``skip_large`` to ``dcmread`` as ``defer_size``, so an
    element over the limit is left on disk with no value in memory. A plain
    ``get_item`` would quietly read it back and *convert* it, handing back a
    str or list rather than bytes -- loading exactly what the limit exists
    to keep out of memory, and slipping past the byte-length skip check.
    While a limit is in force the element stays deferred and reads as
    skipped; only when the limit has been lifted after parsing (tests do
    this) are the raw bytes fetched, so ``skip_large = 0`` means the same
    thing however the dataset was read. Sequences are the exception: Posda
    never size-limits them, so a deferred one is always read back.
    """
    raw = dataset.get_item(tag, keep_deferred=True)
    if not _is_deferred(raw):
        return raw
    if skip_large and _resolve_vr(raw, tag, declared) != "SQ":
        return raw
    return read_deferred_data_element(
        dataset.fileobj_type, dataset.filename, dataset.timestamp, raw
    )


def _is_deferred(raw: object) -> bool:
    """True for a raw element whose value was left on disk by ``defer_size``."""
    return isinstance(raw, RawDataElement) and raw.value is None and raw.length != 0


def _is_skipped(raw: object, vr: str, skip_large: int) -> bool:
    """Mirror Posda::Parser's skip_large seek-past behaviour."""
    if vr == "SQ" or not skip_large:
        return False
    if _is_deferred(raw):
        return True
    value = getattr(raw, "value", None)
    if not isinstance(value, bytes):
        return False
    return len(value) > skip_large


def unpad(value: str, vr: str, sig: str, errors: list[str]) -> str:
    """Reproduce ``Posda::Parser::unpad``.

    Note the ``padnull`` branch: when a UI value ends in a space, Posda
    removes *every* space in the value, not just the trailing one. UI is the
    only VR in Posda's table carrying ``padnull``, and this is the reason
    ``Posda::DB::DicomIod`` has an explicit "Sop class has a space" fixup.
    """
    desc = VR_DESC.get(vr)
    if desc is None:
        return value
    if desc.padnull:
        value = re.sub(r"\0$", "", value)
        if value.endswith(" "):
            errors.append(f"{vr} contains a trailing space (removed) tag: {sig}")
            value = value.replace(" ", "")
    if "\0" in value:
        errors.append(f"{vr} contains nulls (removed) tag: {sig}")
        value = value.replace("\0", "")
    if desc.striptrailing:
        value = re.sub(r" +$", "", value)
    if desc.stripleading:
        value = re.sub(r"^ +", "", value)
    return value


def decode_value(raw: bytes, vr: str, vm: str, sig: str, errors: list[str]) -> object:
    """Reproduce ``Posda::Parser::DecodeElementValue`` for one element."""
    desc = VR_DESC.get(vr)
    if desc is None:
        raise DicomValueError(f"No type in VRDesc for {vr}")

    if desc.type == "text":
        # Posda does no character-set decoding; Perl carries the bytes
        # straight through to DBD::Pg. latin-1 is the byte-preserving
        # equivalent on the Python side.
        text = raw.decode("latin-1")
        if vm == "1":
            return unpad(text, vr, sig, errors)
        return [unpad(part, vr, sig, errors) for part in text.split("\\")]

    if desc.type in _NUMERIC_FORMATS:
        if not raw:
            # A zero-length binary element (e.g. Planar Configuration present
            # with no value) has nothing to unpack. Posda's parser returns
            # before decoding in this case, so it never emits the VM-mismatch
            # warning below; an empty list here would reach psycopg2 as the
            # array literal '{}' and be rejected by integer columns.
            return None
        fmt, size = _NUMERIC_FORMATS[desc.type]
        count = len(raw) // size
        values = list(struct.unpack(f"<{count}{fmt[1]}", raw[: count * size]))
        if desc.type in ("float", "double"):
            # Perl stringifies a float with %.15g on its way to DBI, so an
            # FL of 5.0 reaches the column as "5", not "5.0". Binding a
            # Python float would render the trailing zero and diverge.
            values = [_perl_float(v) for v in values]
        if vm == "1":
            if len(values) != 1:
                errors.append(
                    f"Warning apparent VM mismatch {sig} "
                    f"({desc.type} {vm} vs {len(values)})"
                )
                return values
            return values[0]
        return values

    # "raw" and "seq" are returned untouched; callers that care (ImagePixel)
    # inspect them directly.
    return raw
