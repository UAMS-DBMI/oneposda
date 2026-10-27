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
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
)

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


def build_implicit(**attrs) -> Dataset:
    """Like build(), but written as implicit VR little endian."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3.4"
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = "1.2.3.4"
    for key, value in attrs.items():
        setattr(ds, key, value)
    buf = io.BytesIO()
    ds.save_as(buf, implicit_vr=True, little_endian=True, enforce_file_format=True)
    buf.seek(0)
    return dcmread(buf, force=True)


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


class TestZeroLengthImplicitVR:
    """Zero-length elements in implicit-VR files must decode like explicit.

    pydicom stores a zero-length implicit-VR element as a RawDataElement
    whose value is None (the VR is unknown at read time), and
    Dataset.get_item converts those on access -- handing back PersonName("")
    for a PN, which psycopg2 cannot bind. The shim re-decodes such elements
    from the empty byte string instead.
    """

    def test_empty_pn_is_a_plain_str(self):
        got = ParsedValues(build_implicit(PatientName="")).get("(0010,0010)")
        assert got == ""
        assert type(got) is str

    def test_empty_pn_matches_explicit_vr(self):
        implicit = ParsedValues(build_implicit(PatientName="")).get("(0010,0010)")
        explicit = values_for(PatientName="").get("(0010,0010)")
        assert implicit == explicit

    def test_empty_multi_vm_text_matches_explicit_vr(self):
        # WindowCenter is VM 1-n: both syntaxes must yield the same list,
        # because WindowLevel branches on list-ness.
        implicit = ParsedValues(build_implicit(WindowCenter=None)).get("(0028,1050)")
        explicit = values_for(WindowCenter=None).get("(0028,1050)")
        assert implicit == explicit == [""]

    def test_empty_numeric_matches_explicit_vr(self):
        implicit_errors: list[str] = []
        implicit_values = ParsedValues(
            build_implicit(Rows=None), errors=implicit_errors
        )
        explicit_errors: list[str] = []
        explicit_values = ParsedValues(build(Rows=None), errors=explicit_errors)
        assert implicit_values.get("(0028,0010)") == explicit_values.get(
            "(0028,0010)"
        )
        assert implicit_errors == explicit_errors


class TestZeroLengthNumeric:
    """A binary element that is present but empty reads as no value.

    Posda's parser returns before decoding a zero-length element, so it never
    reaches the numeric unpack and its VM check. Decoding b"" through that
    branch produced [] and a spurious VM-mismatch warning; the empty list
    was then bound by psycopg2 as the array literal '{}', which Postgres
    rejects for integer columns such as image.planar_configuration.
    """

    @pytest.mark.parametrize("builder", [build, build_implicit])
    def test_empty_us_is_none_without_warning(self, builder):
        errors: list[str] = []
        values = ParsedValues(builder(PlanarConfiguration=None), errors=errors)
        assert values.get("(0028,0006)") is None
        assert errors == []

    def test_empty_us_distinct_from_populated(self):
        assert values_for(PlanarConfiguration=0).get("(0028,0006)") == 0

    def test_empty_multi_vm_numeric_is_none(self):
        # (0028,1101) RedPaletteColorLookupTableDescriptor is US VM 3.
        errors: list[str] = []
        values = ParsedValues(
            build(RedPaletteColorLookupTableDescriptor=None), errors=errors
        )
        assert values.get("(0028,1101)") is None
        assert errors == []


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


def rtstruct() -> ParsedValues:
    """A small structure set with two ROIs and a nested frame of reference."""
    from pydicom.sequence import Sequence

    ds = build()
    ds.Modality = "RTSTRUCT"

    contour_image = Dataset()
    contour_image.ReferencedSOPClassUID = CTImageStorage
    contour_image.ReferencedSOPInstanceUID = "1.2.3.700"

    series = Dataset()
    series.SeriesInstanceUID = "1.2.3.801"
    series.ContourImageSequence = Sequence([contour_image])
    study = Dataset()
    study.RTReferencedSeriesSequence = Sequence([series])
    ref_for = Dataset()
    ref_for.FrameOfReferenceUID = "1.2.3.FOR"
    ref_for.RTReferencedStudySequence = Sequence([study])
    ds.ReferencedFrameOfReferenceSequence = Sequence([ref_for])

    rois = []
    for number, name in ((1, "BODY"), (2, "PTV")):
        roi = Dataset()
        roi.ROINumber = number
        roi.ROIName = name
        rois.append(roi)
    ds.StructureSetROISequence = Sequence(rois)
    return ParsedValues(ds)


class TestNavigation:
    """ExtractElementBySig's sequence-navigation suffixes."""

    def test_index_into_a_sequence_then_read(self):
        assert rtstruct().get("(3006,0020)[1](3006,0026)") == "PTV"

    def test_nested_descent(self):
        got = rtstruct().get(
            "(3006,0010)[0](3006,0012)[0](3006,0014)[0](3006,0016)[0](0008,1155)"
        )
        assert got == "1.2.3.700"

    def test_angle_bracket_form_is_equivalent(self):
        # Posda accepts both "[n]rest" and "[n]>rest".
        values = rtstruct()
        assert values.get("(3006,0020)[0]>(3006,0026)") == "BODY"
        assert values.get("(3006,0020)[0](3006,0026)") == "BODY"

    def test_out_of_range_index_is_none(self):
        assert rtstruct().get("(3006,0020)[9](3006,0022)") is None

    def test_missing_sequence_is_none(self):
        assert rtstruct().get("(3006,0039)[0](3006,0084)") is None

    def test_trailing_index_selects_one_value_of_a_multi_valued_element(self):
        # A bare trailing [n] indexes the value itself, not a sequence item.
        values = build(ImageOrientationPatient=["1", "0", "0", "0", "9", "0"])
        assert ParsedValues(values).get("(0020,0037)[4]") == "9"

    def test_trailing_index_on_a_scalar_is_none(self):
        assert ParsedValues(build(PatientID="P1")).get("(0010,0020)[0]") is None

    def test_navigating_a_non_sequence_raises(self):
        values = ParsedValues(build(PatientID="P1"))
        with pytest.raises(DicomValueError):
            values.get("(0010,0020)[0](0008,0060)")


class TestSubstitutions:
    def test_wildcard_yields_one_entry_per_item(self):
        assert rtstruct().substitutions("(3006,0020)[<0>](3006,0022)") == [[0], [1]]

    def test_nested_wildcards_accumulate_indices(self):
        got = rtstruct().substitutions(
            "(3006,0010)[<0>](3006,0012)[<1>](3006,0014)[<2>](3006,0016)[<3>](0008,1155)"
        )
        assert got == [[0, 0, 0, 0]]

    def test_absent_terminal_tag_matches_nothing(self):
        assert rtstruct().substitutions("(3006,0020)[<0>](9999,9999)") == []

    def test_absent_sequence_matches_nothing(self):
        assert rtstruct().substitutions("(3006,0039)[<0>](3006,0042)") == []

    def test_literal_index_restricts_the_walk(self):
        assert rtstruct().substitutions("(3006,0020)[1](3006,0022)") == [[]]

    def test_bad_pattern_raises(self):
        with pytest.raises(DicomValueError):
            rtstruct().substitutions("not a pattern")
