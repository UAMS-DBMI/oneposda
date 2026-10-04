"""Generate synthetic DICOM files exercising the value-semantics edge cases
that the Perl-to-Python port has to reproduce exactly.
"""

import io
import sys
from pathlib import Path

from pydicom.dataelem import RawDataElement
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.tag import Tag
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, ImplicitVRLittleEndian

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "corpus")
OUT.mkdir(parents=True, exist_ok=True)


def raw(ds: Dataset, group: int, element: int, vr: str, value: bytes) -> None:
    """Insert an element verbatim, bypassing pydicom's value conversion.

    Needed for values that are illegal for their VR -- pydicom refuses to
    construct those, but Posda has to cope with them in real data.
    """
    if len(value) % 2:
        value += b" "
    tag = Tag(group, element)
    ds[tag] = RawDataElement(tag, vr, len(value), value, 0, False, True)


def base(sop_instance: str) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = sop_instance
    ds.file_meta.ImplementationClassUID = "1.2.3.4.5"
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = sop_instance
    ds.StudyInstanceUID = "1.2.840.113619.2.1.1"
    ds.SeriesInstanceUID = "1.2.840.113619.2.1.2"
    return ds


def write(ds: Dataset, name: str, transfer_syntax=ExplicitVRLittleEndian) -> None:
    ds.file_meta.TransferSyntaxUID = transfer_syntax
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    (OUT / name).write_bytes(buf.getvalue())
    print(f"wrote {name} ({len(buf.getvalue())} bytes)")


# --- A: an ordinary CT slice -------------------------------------------------
a = base("1.2.3.100")
a.PatientName = "Doe^John"
a.PatientID = "PAT001"
a.PatientBirthDate = "19700615"
a.PatientSex = "M"
a.StudyDate = "20240101"
a.StudyTime = "143000"
a.SeriesDate = "20240101"
a.SeriesTime = "143005.25"
a.Modality = "CT"
a.SeriesNumber = "2"
a.InstanceNumber = "1"
a.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
a.WindowCenter = "45"  # DS, dictionary VM 1-n, single value present
a.WindowWidth = "400"
a.Rows = 512
a.Columns = 512
a.SamplesPerPixel = 1
a.BitsAllocated = 16
a.PhotometricInterpretation = "MONOCHROME2"
a.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
a.ImagePositionPatient = [-250.0, -250.0, 10.5]
a.PixelSpacing = [0.5, 0.5]
a.RescaleSlope = "1"
a.RescaleIntercept = "-1024"
a.KVP = "120"
a.ConvolutionKernel = "STANDARD"
write(a, "a_normal.dcm")

# --- B: empty / padded / oversized values ------------------------------------
b = base("1.2.3.101")
b.PatientName = "Smith^Jane^^Dr^"  # trailing component delimiter
b.PatientID = "PAT002"
b.PatientBirthDate = ""  # -> the ubiquitous 'Bad date ""' row
b.StudyDate = "20240229"  # valid leap day
b.StudyTime = "0930"  # too short for Posda's TM regex
b.Modality = "CT"
b.SeriesNumber = " 12 "  # UndefIfNotNumber keeps original text
b.ImageType = ["DERIVED"]  # single value, dictionary VM 2-n
b.WindowCenter = "45\\50"  # genuinely multi-valued
b.WindowWidth = "400\\500"
b.WindowCenterWidthExplanation = "BRAIN\\SUBDURAL"
b.StudyDescription = "X" * 300  # > skip_large (256) -> must read as absent
b.ConvolutionKernel = "BONE\\SHARP"
b.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
write(b, "b_edges.dcm")

# --- C: malformed values -----------------------------------------------------
c = base("1.2.3.102")
c.PatientName = "Trailing^Spaces   "  # PN striptrailing
c.PatientID = "  Leading"  # LO stripleading
c.PatientBirthDate = "1970061"  # 7 chars: fails ^(....)(..)(..)$
c.StudyDate = "20241301"  # month 13
c.StudyTime = "99xx99"  # not a time at all
c.Modality = "CT"
raw(c, 0x0020, 0x0011, "IS", b"abc")  # UndefIfNotNumber rejects
c.ImageType = ["ORIGINAL", "PRIMARY"]
c.WindowCenter = "0"  # Perl-falsy string
c.WindowWidth = "400"
c.SeriesDescription = "has\\backslash"  # LO with VM 1-n and an embedded sep
write(c, "c_malformed.dcm")

# --- D: implicit VR ----------------------------------------------------------
d = base("1.2.3.103")
d.PatientName = "Implicit^VR"
d.PatientID = "PAT004"
d.PatientBirthDate = "19551105"
d.StudyDate = "19551105"
d.StudyTime = "010203.456"
d.Modality = "CT"
d.SeriesNumber = "7"
d.WindowCenter = "40"
d.WindowWidth = "350"
d.ImageType = ["ORIGINAL", "SECONDARY"]
write(d, "d_implicit.dcm", ImplicitVRLittleEndian)
