"""Corpus files carrying pixel data, to exercise ImagePixel and everything
that depends on the image_id it publishes: ImagePlane, SlopeIntercept and
WindowLevel -- including WindowLevel's explanation branch, which is where the
shadowed-loop-variable defect lives.
"""

import io
import sys
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

RT_DOSE = "1.2.840.10008.5.1.4.1.1.481.2"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "corpus")
OUT.mkdir(parents=True, exist_ok=True)


def ct(name: str, sop: str = "1.2.3.200", pixels: bytes = None, **attrs):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = attrs.pop("sop_class", CTImageStorage)
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.ImplementationClassUID = "1.2.3.4.5"
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = sop
    ds.StudyInstanceUID = "1.2.3.210"
    ds.SeriesInstanceUID = "1.2.3.211"
    ds.Modality = "CT"
    ds.PatientName = "Pixel^Test"
    ds.PatientID = "PIX001"
    ds.PatientBirthDate = "19600102"
    ds.StudyDate = "20240401"
    ds.StudyTime = "120000"
    ds.FrameOfReferenceUID = "1.2.3.220"
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [-100.0, -100.0, 5.0]
    ds.PixelSpacing = [0.7, 0.7]
    ds.RescaleSlope = "1"
    ds.RescaleIntercept = "-1024"
    ds.Rows, ds.Columns = 4, 4
    ds.SamplesPerPixel = 1
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 8, 8, 7
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
    ds.KVP = "120"
    for key, value in attrs.items():
        setattr(ds, key, value)
    if pixels is not None:
        ds.PixelData = pixels
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    (OUT / name).write_bytes(buf.getvalue())
    print(f"  {name} ({len(buf.getvalue())} bytes)")


PIX_A = bytes(range(16))
PIX_B = bytes(range(16, 32))

# Single window centre/width: the common case, and the one that proves
# dictionary-VM boxing is what lets WindowLevel write anything at all.
ct("p1_single_window.dcm", "1.2.3.201", PIX_A, WindowCenter="45", WindowWidth="400")

# Same pixel data as p1: exercises the (dead) dedup lookup path.
ct("p2_same_pixels.dcm", "1.2.3.202", PIX_A, WindowCenter="45", WindowWidth="400")

# Multi-valued window settings with no explanation: the else branch, one
# file_win_lev row per value.
ct(
    "p3_multi_window.dcm",
    "1.2.3.203",
    PIX_B,
    WindowCenter="45\\50",
    WindowWidth="400\\500",
)

# Multi-valued *with* an explanation: the branch with the shadowed loop
# variable, which writes N^2 rows instead of N.
ct(
    "p4_window_explanation.dcm",
    "1.2.3.204",
    bytes(range(32, 48)),
    WindowCenter="45\\50",
    WindowWidth="400\\500",
    WindowCenterWidthExplanation="BRAIN\\SUBDURAL",
)

# RT Dose carries pixel data and runs RTDose after ImagePixel, so it proves
# image_id survives the hand-off to the Perl bridge.
ct(
    "p5_rtdose.dcm",
    "1.2.3.205",
    bytes(range(48, 64)),
    sop_class=RT_DOSE,
    Modality="RTDOSE",
    DoseUnits="GY",
    DoseType="PHYSICAL",
    DoseSummationType="PLAN",
    GridFrameOffsetVector=[0.0],
    DoseGridScaling="0.001",
    NumberOfFrames="1",
)

print("done")
