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
from pydicom.sequence import Sequence

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
# "(3006,0010)[0](3006,00c0)[1](3006,00c2)".
_SIG_HEAD = re.compile(r"^\(([0-9a-fA-F]{4}),([0-9a-fA-F]{4})\)(.*)$")
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
        """Public-tag read, equivalent to ``$ds->ExtractElementBySig($sig)``.

        Supports the navigation suffixes the RT handlers use: ``[n]`` to
        index into a multi-valued element or a sequence, and ``[n]rest`` (or
        ``[n]>rest``) to descend into sequence item *n* and carry on.
        """
        match = _SIG_HEAD.match(sig)
        if match is None:
            raise DicomValueError(f"Sig ({sig}) didn't match")
        tag = (int(match.group(1), 16) << 16) | int(match.group(2), 16)
        remain = match.group(3)
        if not remain:
            return self._read(self.dataset, tag, sig)
        return self._navigate(self.dataset, tag, remain, sig)

    def _navigate(self, dataset: Dataset, tag: int, remain: str, sig: str) -> object:
        """Follow a navigation suffix, mirroring ExtractElementBySig."""
        if dataset is None or tag not in dataset:
            return None

        # A bare trailing [n] indexes whatever the value is -- Posda checks
        # this before it checks for SQ, so it serves both multi-valued
        # elements and sequences.
        match = _INDEX_ONLY.match(remain)
        if match is not None:
            value = self._value_for_navigation(dataset, tag, sig)
            if not isinstance(value, (list, Sequence)):
                return None
            index = int(match.group(1))
            return value[index] if index < len(value) else None

        vr = _resolve_vr(dataset.get_item(tag), tag)
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

        head = _SIG_HEAD.match(rest)
        if head is None:
            raise DicomValueError(f"Sig ({rest}) didn't match")
        next_tag = (int(head.group(1), 16) << 16) | int(head.group(2), 16)
        next_remain = head.group(3)
        if not next_remain:
            return self._read(item, next_tag, rest)
        return self._navigate(item, next_tag, next_remain, rest)

    def _value_for_navigation(self, dataset: Dataset, tag: int, sig: str) -> object:
        """The value to index into for a trailing ``[n]``.

        Sequences have to come from ``dataset[tag].value`` -- pydicom's
        ``get_item`` hands back the undecoded bytes for SQ, which cannot be
        indexed by item.
        """
        vr = _resolve_vr(dataset.get_item(tag), tag)
        if vr == "SQ":
            return dataset[tag].value
        return self._read(dataset, tag, sig)

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

    def _substitute(
        self,
        dataset: Dataset,
        pattern: str,
        accum: list[int],
        matches: list[list[int]],
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
                    raise DicomValueError("specified item of SQ is not a dataset")
                self._substitute(items[position], remain, accum, matches)
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
                    self._substitute(item, remain, accum + [position], matches)
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
        """Private-tag read, equivalent to ``$ds->Get('(0013,"CTP",10)')``."""
        match = _PRIVATE_SIG.match(sig)
        if match is None:
            raise DicomValueError(f"Sig ({sig}) didn't match")
        group = int(match.group(1), 16)
        creator = match.group(2)
        offset = int(match.group(3), 16)
        if not group & 1:
            raise DicomValueError(f"only private groups have owner: {sig}")
        try:
            block = self.dataset.private_block(group, creator)
        except KeyError:
            return None
        tag = block.get_tag(offset)
        return self._read(self.dataset, int(tag), sig)

    def _read(self, dataset: Dataset, tag: int, sig: str) -> object:
        raw = dataset.get_item(tag)
        if raw is None:
            return None
        vr = _resolve_vr(raw, tag)
        if vr is None:
            return None
        if _is_skipped(raw, vr, self.skip_large):
            return None
        value = raw.value if isinstance(raw, RawDataElement) else raw.value
        if not isinstance(value, bytes):
            # Already-converted element (e.g. one pydicom eagerly decoded).
            return value
        return decode_value(value, vr, _dictionary_vm(tag), sig, self.errors)


def _dictionary_vm(tag: int) -> str:
    try:
        return dictionary_VM(tag)
    except KeyError:
        # Posda falls back to treating unknown tags as multi-valued.
        return "1-n"


def _resolve_vr(raw: object, tag: int) -> str | None:
    vr = getattr(raw, "VR", None)
    if vr in (None, "UN", ""):
        try:
            vr = dictionary_VR(tag)
        except KeyError:
            return vr if vr else None
    return str(vr) if vr else None


def _is_skipped(raw: object, vr: str, skip_large: int) -> bool:
    """Mirror Posda::Parser's skip_large seek-past behaviour."""
    if vr == "SQ" or not skip_large:
        return False
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
        fmt, size = _NUMERIC_FORMATS[desc.type]
        count = len(raw) // size
        values = list(struct.unpack(f"<{count}{fmt[1]}", raw[: count * size]))
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
