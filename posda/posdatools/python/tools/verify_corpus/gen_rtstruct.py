"""Generate an RT Structure Set exercising the sequence navigation the RT
handlers rely on: referenced frames of reference, contour images, ROIs,
contours and ROI observations.
"""

import io
import sys
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "corpus")
OUT.mkdir(parents=True, exist_ok=True)

RT_STRUCT = "1.2.840.10008.5.1.4.1.1.481.3"
CT = "1.2.840.10008.5.1.4.1.1.2"
FOR_UID = "1.2.840.113619.2.55.3.FOR"

ds = Dataset()
ds.file_meta = FileMetaDataset()
ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
ds.file_meta.MediaStorageSOPClassUID = RT_STRUCT
ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3.900"
ds.file_meta.ImplementationClassUID = "1.2.3.4.5"

ds.SOPClassUID = RT_STRUCT
ds.SOPInstanceUID = "1.2.3.900"
ds.StudyInstanceUID = "1.2.3.800"
ds.SeriesInstanceUID = "1.2.3.801"
ds.Modality = "RTSTRUCT"
ds.PatientName = "RT^Test"
ds.PatientID = "RT001"
ds.PatientBirthDate = "19800101"
ds.StudyDate = "20240301"
ds.StudyTime = "101500"
ds.InstanceNumber = "1"
ds.Manufacturer = "Posda Test"

# (3006,0002..0009)
ds.StructureSetLabel = "TestSS"
ds.StructureSetName = "TestSSName"
ds.StructureSetDescription = "generated for the ingest port"
ds.StructureSetDate = "20240301"
ds.StructureSetTime = "101530"

# (3006,0010) ReferencedFrameOfReferenceSequence
contour_image = Dataset()
contour_image.ReferencedSOPClassUID = CT
contour_image.ReferencedSOPInstanceUID = "1.2.3.700"

rt_series = Dataset()
rt_series.SeriesInstanceUID = "1.2.3.801"
rt_series.ContourImageSequence = Sequence([contour_image])

rt_study = Dataset()
rt_study.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
rt_study.ReferencedSOPInstanceUID = "1.2.3.800"
rt_study.RTReferencedSeriesSequence = Sequence([rt_series])

ref_for = Dataset()
ref_for.FrameOfReferenceUID = FOR_UID
ref_for.RTReferencedStudySequence = Sequence([rt_study])

# (3006,00c0) FrameOfReferenceRelationshipSequence
related = Dataset()
related.RelatedFrameOfReferenceUID = "1.2.840.113619.2.55.3.FOR2"
related.FrameOfReferenceTransformationType = "RIGID"
related.FrameOfReferenceTransformationMatrix = [
    1,
    0,
    0,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    1,
]
related.FrameOfReferenceTransformationComment = "identity"
ref_for.FrameOfReferenceRelationshipSequence = Sequence([related])

ds.ReferencedFrameOfReferenceSequence = Sequence([ref_for])

# (3006,0020) StructureSetROISequence
rois = []
for number, name in ((1, "BODY"), (2, "PTV")):
    roi = Dataset()
    roi.ROINumber = number
    roi.ReferencedFrameOfReferenceUID = FOR_UID
    roi.ROIName = name
    roi.ROIDescription = f"{name} description"
    roi.ROIGenerationAlgorithm = "MANUAL"
    rois.append(roi)
ds.StructureSetROISequence = Sequence(rois)

# (3006,0039) ROIContourSequence
roi_contours = []
for number, colour in ((1, [255, 0, 0]), (2, [0, 255, 0])):
    contour = Dataset()
    contour.ContourGeometricType = "CLOSED_PLANAR"
    contour.NumberOfContourPoints = 4
    contour.ContourData = [
        0.0,
        0.0,
        10.0,
        10.0,
        0.0,
        10.0,
        10.0,
        10.0,
        10.0,
        0.0,
        10.0,
        10.0,
    ]
    contour.ContourImageSequence = Sequence([contour_image])

    roi_contour = Dataset()
    roi_contour.ReferencedROINumber = number
    roi_contour.ROIDisplayColor = colour
    roi_contour.ContourSequence = Sequence([contour])
    roi_contours.append(roi_contour)
ds.ROIContourSequence = Sequence(roi_contours)

# (3006,0080) RTROIObservationsSequence
observations = []
for number, interpreted in ((1, "EXTERNAL"), (2, "PTV")):
    obs = Dataset()
    obs.ObservationNumber = number
    obs.ReferencedROINumber = number
    obs.ROIObservationLabel = f"obs{number}"
    obs.RTROIInterpretedType = interpreted
    obs.ROIInterpreter = ""
    observations.append(obs)
ds.RTROIObservationsSequence = Sequence(observations)

out = OUT / "rtstruct.dcm"
buf = io.BytesIO()
ds.save_as(buf, enforce_file_format=True)
out.write_bytes(buf.getvalue())
print(f"wrote {out} ({len(buf.getvalue())} bytes)")
