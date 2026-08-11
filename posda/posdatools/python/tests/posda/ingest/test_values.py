"""Tests for the Posda::Parser value semantics shim.

Every expectation here was captured by running the real Perl
(``Posda::NewTry`` + ``ExtractElementBySig``) inside the
posda-fast-file-process container over the same synthetic files and diffing
the results. These are regression locks on *Posda's* behaviour, not on
correct DICOM handling -- several of them encode outright bugs that the port
is required to reproduce until they are fixed separately.
"""

import io

import pytest
from pydicom import dcmread
from pydicom.dataelem import RawDataElement
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.tag import Tag
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

from posda.ingest.values import SKIP_LARGE, DicomValueError, ParsedValues, unpad


def build(**attrs) -> Dataset:
    """Round-trip a dataset through bytes so elements arrive as raw values."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3.4"
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4"
    for key, value in attrs.items():
        setattr(ds, key, value)
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    buf.seek(0)
    return dcmread(buf, force=True)


def values_for(**attrs) -> ParsedValues:
    return ParsedValues(build(**attrs))


class TestArrayness:
    """Array-ness follows the dictionary VM, not the runtime value."""

    def test_single_value_of_multi_vm_tag_is_a_list(self):
        # WindowCenter is VM 1-n, so Posda returns a list even for one value.
        # Posda::DB::Modules::WindowLevel bails out unless it gets a list, so
        # returning a bare string here silently drops every file_win_lev row.
        assert values_for(WindowCenter="45").get("(0028,1050)") == ["45"]

    def test_multiple_values_of_multi_vm_tag(self):
        got = values_for(WindowCenter="45\\50").get("(0028,1050)")
        assert got == ["45", "50"]

    def test_vm_one_tag_is_a_scalar(self):
        assert values_for(PatientID="PAT001").get("(0010,0020)") == "PAT001"

    def test_vm_one_tag_does_not_split_on_backslash(self):
        # SeriesDescription is VM 1: an embedded backslash is data, not a
        # value separator.
        got = values_for(SeriesDescription="has\\backslash").get("(0008,103e)")
        assert got == "has\\backslash"

    def test_numeric_vm_one_tag_is_a_scalar_int(self):
        assert values_for(Rows=512).get("(0028,0010)") == 512


class TestPadding:
    """unpad() follows Posda's VR table, which is not pydicom's."""

    def test_pn_strips_trailing_spaces(self):
        got = values_for(PatientName="Trailing^Spaces   ").get("(0010,0010)")
        assert got == "Trailing^Spaces"

    def test_lo_strips_leading_spaces(self):
        assert values_for(PatientID="  Leading").get("(0010,0020)") == "Leading"

    def test_da_does_not_strip(self):
        # DA carries neither striptrailing nor stripleading in Posda's table,
        # so a padded date keeps its space and later fails the date regex.
        ds = build()
        tag = Tag(0x0010, 0x0030)
        ds[tag] = RawDataElement(tag, "DA", 8, b"1970061 ", 0, False, True)
        assert ParsedValues(ds).get("(0010,0030)") == "1970061 "

    def test_ui_trailing_null_removed(self):
        got = values_for(SOPClassUID=CTImageStorage).get("(0008,0016)")
        assert got == CTImageStorage

    def test_ui_trailing_space_removes_every_space(self):
        # padnull's branch does s/ //g, not a trailing-only strip. UI is the
        # only VR with padnull, and this is why DicomIod carries an explicit
        # "Sop class has a space" fixup.
        errors: list[str] = []
        assert unpad("1.2.3 4 ", "UI", "(0008,0016)", errors) == "1.2.34"
        assert errors == ["UI contains a trailing space (removed) tag: (0008,0016)"]

    def test_embedded_nulls_removed_with_an_error(self):
        errors: list[str] = []
        assert unpad("AB\0CD", "LO", "(0008,1030)", errors) == "ABCD"
        assert errors == ["LO contains nulls (removed) tag: (0008,1030)"]


class TestSkipLarge:
    """Posda::NewTry parses with skip_large => 256."""

    def test_value_over_the_limit_reads_as_absent(self):
        got = values_for(StudyDescription="X" * 300).get("(0008,1030)")
        assert got is None

    def test_value_at_the_limit_is_kept(self):
        text = "X" * SKIP_LARGE
        assert values_for(StudyDescription=text).get("(0008,1030)") == text

    def test_limit_is_configurable(self):
        values = values_for(StudyDescription="X" * 300)
        values.skip_large = 0
        assert values.get("(0008,1030)") == "X" * 300


class TestLookup:
    def test_absent_tag_is_none(self):
        assert values_for().get("(0008,1030)") is None

    def test_malformed_signature_raises(self):
        with pytest.raises(DicomValueError):
            values_for().get("0008,1030")

    def test_private_tag_read(self):
        ds = build()
        block = ds.private_block(0x0013, "CTP", create=True)
        block.add_new(0x10, "LO", "MyProject")
        assert ParsedValues(ds).get_private('(0013,"CTP",10)') == "MyProject"

    def test_private_tag_absent_creator_is_none(self):
        assert values_for().get_private('(0013,"CTP",10)') is None

    def test_private_signature_requires_odd_group(self):
        with pytest.raises(DicomValueError):
            values_for().get_private('(0012,"CTP",10)')
