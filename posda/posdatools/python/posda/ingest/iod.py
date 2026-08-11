"""SOP-class dispatch, ported from ``Posda::DB::DicomIod``.

``import_dataset`` is the entry point the worker calls once a file has been
identified as a parseable DICOM instance. It writes ``ctp_file`` and
``file_sop_common``, then runs the handler list registered for the SOP class,
and finally flushes the accumulated complaints into ``dicom_process_errors``.

The ``SOP_HANDLERS`` table below is generated from ``DicomIod.pm`` rather
than transcribed -- 81 SOP classes and 478 handler references are too many to
retype safely. Handler names are strings resolved against
``modules.HANDLERS`` at call time so that the RT bridge can substitute its
own implementations without touching this table.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from posda.ingest import fixes, modules, rt_bridge, sopclasses, specs
from posda.ingest.values import ParsedValues

# Sentinel so that rt_runner=None can mean "skip RT handlers" while the
# default still means "use the Perl bridge".
_UNSET = object()

if TYPE_CHECKING:
    from posda.ingest.db import Database

log = logging.getLogger(__name__)

_CREATION_TIME_RE = re.compile(r"^(\d\d)(\d\d)(\d\d)$")
_CREATION_TIME_FRAC_RE = re.compile(r"^(\d\d)(\d\d)(\d\d)\.(\d+)$")
_CREATION_DATE_RE = re.compile(r"^(\d\d\d\d)(\d\d)(\d\d)$")
_WHITESPACE_RE = re.compile(r"\s")


@dataclass(frozen=True)
class SopClass:
    name: str
    handlers: tuple[str, ...]


# Handlers implemented in Perl only, dispatched through the RT bridge. Every
# one of these needs Posda::Dataset's sequence navigation (the "[<0>]"
# signature form), which is why they were left on the Perl side for now.
RT_HANDLERS = frozenset(
    {
        "RtPlan",
        "RtPrescription",
        "RtToleranceTables",
        "RtPatientSetup",
        "RtFractionScheme",
        "RtBeams",
        "RTDose",
        "RTDvh",
    }
)


SOP_HANDLERS: dict[str, SopClass] = {
    "1.2.840.10008.5.1.1.29": SopClass(
        name="Hardcopy Grayscale Image Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.1.30": SopClass(
        name="Hardcopy Color Image Storage  - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.11.2": SopClass(
        name="Color Softcopy Presentation State Storage SOP Class",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.104.1": SopClass(
        name="Encapsulated PDF Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.130": SopClass(
        name="Enhanced PET Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.67": SopClass(
        name="X-Ray Radiation Dose SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1": SopClass(
        name="Computed Radiography Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "SlopeIntercept",
            "WindowLevel",
            "CRImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1.1": SopClass(
        name="Digital X-Ray Image Storage - For Presentation",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "SlopeIntercept",
            "WindowLevel",
            "FrameOfReference",
            "ContrastBolus",
            "DXImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1.1.1": SopClass(
        name="Digital X-Ray Image Storage - For Processing",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "SlopeIntercept",
            "WindowLevel",
            "FrameOfReference",
            "ContrastBolus",
            "DXImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1.2": SopClass(
        name="Digital Mammography X-Ray Image Storage - For Presentation",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "WindowLevel",
            "SlopeIntercept",
            "FrameOfReference",
            "ContrastBolus",
            "DXImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1.2.1": SopClass(
        name="Digital Mammography X-Ray Image Storage - For Processing",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "SlopeIntercept",
            "WindowLevel",
            "FrameOfReference",
            "ContrastBolus",
            "DXImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1.3": SopClass(
        name="Digital Intra-oral X-Ray Image Storage - For Presentation",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "SlopeIntercept",
            "WindowLevel",
            "FrameOfReference",
            "ContrastBolus",
            "DXImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.1.3.1": SopClass(
        name="Digital Intra-oral X-Ray Image Storage - For Processing",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "SlopeIntercept",
            "WindowLevel",
            "FrameOfReference",
            "ContrastBolus",
            "DXImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.2": SopClass(
        name="CT Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "SlopeIntercept",
            "WindowLevel",
            "CTImage",
            "ContrastBolus",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.3": SopClass(
        name="Ultrasound Multiframe Image Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.3.1": SopClass(
        name="Ultrasound Multiframe Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "SlopeIntercept",
            "WindowLevel",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.4": SopClass(
        name="MR Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "WindowLevel",
            "ContrastBolus",
            "MRImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.4.1": SopClass(
        name="Enhanced MR Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.5": SopClass(
        name="Nuclear Medicine Image Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.6": SopClass(
        name="Ultrasound Image Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "Synchronization",
            "ImagePixel",
            "USImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.6.1": SopClass(
        name="Ultrasound Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "Synchronization",
            "ImagePixel",
            "USImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.7": SopClass(
        name="Secondary Capture Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.7.1": SopClass(
        name="Multiframe Single Bit Secondary Capture Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.7.2": SopClass(
        name="Multiframe Grayscale Byte Secondary Capture Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.7.3": SopClass(
        name="Multiframe Grayscale Word Secondary Capture Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.7.4": SopClass(
        name="Multiframe True Color Secondary Capture Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.8": SopClass(
        name="Standalone Overlay Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9": SopClass(
        name="Standalone Curve Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.1.1": SopClass(
        name="Twelve Lead ECG Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "Synchronization",
            "WaveformIdentification",
            "AcquisitionContext",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.1.2": SopClass(
        name="General ECG Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "Synchronization",
            "WaveformIdentification",
            "AcquisitionContext",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.1.3": SopClass(
        name="Ambulatory ECG Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "Synchronization",
            "WaveformIdentification",
            "Waveform",
            "AcquisitionContext",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.2.1": SopClass(
        name="Hemodynamic Waveform Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "Synchronization",
            "WaveformIdentification",
            "Waveform",
            "AcquisitionContext",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.3.1": SopClass(
        name="Cardiac Electrophysiology Waveform Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "Synchronization",
            "WaveformIdentification",
            "Waveform",
            "AcquisitionContext",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.4.1": SopClass(
        name="Basic Voice Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "Synchronization",
            "WaveformIdentification",
            "Waveform",
            "AcquisitionContext",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.10": SopClass(
        name="Standalone Modality LUT Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.11": SopClass(
        name="Standalone VOI LUT Storage - Retired",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.11.1": SopClass(
        name="Grayscale Softcopy Presentation State Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "PresentationState",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.12.1": SopClass(
        name="Xray Angiographic Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "SlopeIntercept",
            "WindowLevel",
            "CTImage",
            "ContrastBolus",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.12.2": SopClass(
        name="Xray RadioFlouroscopic Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.12.3": SopClass(
        name="Xray Angiographic Biplane Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.20": SopClass(
        name="Nuclear Medicine Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "SlopeIntercept",
            "WindowLevel",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.66": SopClass(
        name="Raw DataStorage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.66.1": SopClass(
        name="Spatial Registration Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "SpatialRegistration",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.66.2": SopClass(
        name="Spatial Fiducials Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "SpatialFiducials",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.66.3": SopClass(
        name="Deformable Spatial Registration Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "SpatialRegistration",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.66.4": SopClass(
        name="Segmentation Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "ImagePixel",
            "ImagePlane",
            "WindowLevel",
            "Segmentation",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.66.5": SopClass(
        name="Surface Segmentation Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "FrameOfReference",
            "SurfaceSegmentation",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.67": SopClass(
        name="Real World Mapping Values",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "RealWorldMapping",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.1.1": SopClass(
        name="Visible Light Endoscopic Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.1.2": SopClass(
        name="Visible Light Microscopic Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.1.3": SopClass(
        name="Visible Light Slide Coordinates Microscopic Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.1.4": SopClass(
        name="Visible Light Photographic Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.11": SopClass(
        name="Basic Text SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "SRSeries",
            "Equipment",
            "Document",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.22": SopClass(
        name="Enhanced SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "SRSeries",
            "Equipment",
            "Document",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.33": SopClass(
        name="Comprehensive SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "SRSeries",
            "Equipment",
            "Document",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.34": SopClass(
        name="Comprehensive 3D SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "SRSeries",
            "Equipment",
            "Document",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.50": SopClass(
        name="Mammography CAD SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.59": SopClass(
        name="Key Object Selection Document Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "KeySeries",
            "Equipment",
            "KeyObjectDocument",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.71": SopClass(
        name="Acquisition Context SR Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.128": SopClass(
        name="Positron Emission Tomography Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "SlopeIntercept",
            "WindowLevel",
            "PetImage",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.129": SopClass(
        name="Standalone PET Curve Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.1": SopClass(
        name="RT Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "FrameOfReference",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.2": SopClass(
        name="RT Dose Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "RTDose",
            "RTDvh",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.3": SopClass(
        name="RT Structure Set Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "StructureSet",
            "RoiContour",
            "RtRoiObservations",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.4": SopClass(
        name="RT Beams Treatment Record Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.5": SopClass(
        name="RT Plan Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "RtPlan",
            "RtPrescription",
            "RtToleranceTables",
            "RtPatientSetup",
            "RtFractionScheme",
            "RtBeams",
            "RtBrachy",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.8": SopClass(
        name="RT Ion Plan Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.6": SopClass(
        name="RT Brachy Treatment Record Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.481.7": SopClass(
        name="RT Treatment Summary Record Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.1": SopClass(
        name="Visible Light Image Storage - Trial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.2": SopClass(
        name="Visible Light Multiframe Image Storage - Trial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.9.1": SopClass(
        name="WaveformStorageTrial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.1": SopClass(
        name="TextSRStorageTrial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.2": SopClass(
        name="AudioSRStorageTrial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.3": SopClass(
        name="DetailSRStorageTrial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.88.4": SopClass(
        name="ComprehensiveSRStorageTrial",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.2.1": SopClass(
        name="Enhanced CT Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.13.1.3": SopClass(
        name="Breast Tomosynthesis Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.13.1.4": SopClass(
        name="Breast Projection X-Ray Image Storage - For Presentation",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.13.1.5": SopClass(
        name="Breast Projection X-Ray Image Storage - For Processing",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
        ),
    ),
    "1.2.840.10008.5.1.4.1.1.77.1.6": SopClass(
        name="VL Whole Slide Microscopy Image Storage",
        handlers=(
            "Patient",
            "Study",
            "Series",
            "Equipment",
            "ImagePixel",
            "ImagePlane",
            "FrameOfReference",
            "SlopeIntercept",
            "WindowLevel",
        ),
    ),
}


def sop_class_description(sop_class: str) -> str:
    """The description stored in ``dicom_file.dicom_file_type``.

    Deliberately delegates to the ``$SopCl`` table rather than using
    ``SopClass.name`` from the handler table below. The two disagree for 41
    of the 81 SOP classes that have handlers -- DicomIod.pm says
    "Xray Angiographic Image Storage" where DataDict.pm says "X-Ray
    Angiographic Image Storage" -- and it is DataDict's spelling that
    FastFileProcessWorker.pl writes to the column.

    ``SopClass.name`` is used only in the "No handlers for ..." error text,
    which is the one place the Perl also uses it.
    """
    return sopclasses.sop_class_description(sop_class)


def import_dataset(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    sop_class: str | None,
    description: str | None = None,
    import_event_id: object = None,
    handlers: dict[str, object] | None = None,
    rt_runner: object = _UNSET,
) -> list[str]:
    """Port of ``Posda::DB::DicomIod::Import``.

    ``rt_runner`` receives any contiguous block of RT handlers; it defaults
    to the Perl bridge. Pass ``None`` to skip RT handling entirely, which is
    what the tests do when they only care about the Python handlers.

    Returns the error strings that were written to ``dicom_process_errors``.
    """
    errors: list[str] = []
    registry = handlers if handlers is not None else modules.HANDLERS
    if rt_runner is _UNSET:
        rt_runner = rt_bridge.run_block

    _insert_ctp(db, values, file_id)
    parms = _sop_common_params(values, errors)

    # The Perl reassigns its $sop_class from the (possibly repaired) value
    # before looking up handlers, so the same variable drives dispatch.
    sop_class = _repair_sop_class(parms, sop_class, errors)

    if parms.get("sop_class") is not None and parms.get("sop_instance") is not None:
        _insert_sop_common(db, file_id, parms)
        _run_handlers(
            db,
            values,
            file_id,
            sop_class,
            import_event_id,
            errors,
            registry,
            rt_runner,
        )
    else:
        if not parms.get("sop_class"):
            errors.append(f"file {file_id} has no SOP class")
        if not parms.get("sop_instance"):
            errors.append(f"file {file_id} has no SOP instance")

    for error in errors:
        db.execute(
            "insert into dicom_process_errors (file_id, error_msg) values (%s, %s)",
            [file_id, error],
        )
    return errors


def _insert_ctp(db: "Database", values: ParsedValues, file_id: int) -> None:
    """Write ``ctp_file`` if any of the CTP identity tags carry a value."""
    parms = {key: values.get_private(sig) for key, sig in specs.CTP.params.items()}
    # Mirrors the Perl's guard exactly, including its reference to a
    # 'visibility' key that is never populated.
    triggers = (
        "project_name",
        "trial_name",
        "site_name",
        "site_id",
        "file_visibility",
        "visibility",
    )
    if not any(parms.get(key) not in (None, "") for key in triggers):
        return
    db.execute(
        "insert into ctp_file"
        " (file_id, project_name, trial_name, site_name, site_id,"
        "  file_visibility, batch, study_year)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s)",
        [
            file_id,
            parms.get("project_name"),
            parms.get("trial_name"),
            parms.get("site_name"),
            parms.get("site_id"),
            parms.get("file_visibility"),
            parms.get("batch"),
            parms.get("study_year"),
        ],
    )


def _sop_common_params(values: ParsedValues, errors: list[str]) -> dict:
    parms = {key: values.get(sig) for key, sig in specs.SOP_COMMON.params.items()}

    if isinstance(parms.get("spec_char_set"), list):
        parms["spec_char_set"] = "\\".join(parms["spec_char_set"])

    parms["creation_time"] = _creation_time(parms.get("creation_time"), errors)
    parms["creation_date"] = _creation_date(parms.get("creation_date"), errors)

    if isinstance(parms.get("related_general_sop_class"), list):
        parms["related_general_sop_class"] = "\\".join(
            parms["related_general_sop_class"]
        )
    return parms


def _creation_time(value: object, errors: list[str]) -> object:
    if value is None:
        return None
    text = str(value)
    match = _CREATION_TIME_RE.match(text)
    if match:
        return f"{match.group(1)}:{match.group(2)}:{match.group(3)}"
    match = _CREATION_TIME_FRAC_RE.match(text)
    if match:
        return f"{match.group(1)}:{match.group(2)}:{match.group(3)}.{match.group(4)}"
    errors.append(f'Illegal creation time: "{text}"')
    return None


def _creation_date(value: object, errors: list[str]) -> object:
    if value is None:
        return None
    text = str(value)
    match = _CREATION_DATE_RE.match(text)
    if match is None:
        errors.append(f"Illegal creation date: {text}")
        return None
    year, month, day = match.group(1), match.group(2), match.group(3)
    if 0 < int(month) < 13 and 0 < int(day) < 32:
        # Note the Perl interpolates the captures directly here rather than
        # using sprintf as GetAttrs::Date does; the captures are already
        # fixed width so the result is the same.
        return f"{year}/{month}/{day}"
    errors.append(f'Illegal creation date: "{text}"')
    return None


def _repair_sop_class(
    parms: dict, sop_class: str | None, errors: list[str]
) -> str | None:
    value = parms.get("sop_class")
    if value is None or not _WHITESPACE_RE.search(str(value)):
        return sop_class
    errors.append(f'Sop class has a space: "{value}"')
    repaired = _WHITESPACE_RE.sub("", str(value))
    parms["sop_class"] = repaired
    errors.append(f'substitution: "{repaired}"')
    return repaired


def _insert_sop_common(db: "Database", file_id: int, parms: dict) -> None:
    db.execute(
        "insert into file_sop_common"
        " (file_id, sop_class_uid, sop_instance_uid, specific_character_set,"
        "  creation_date, creation_time, creator_uid,"
        "  related_general_sop_class, original_specialized_sop_class,"
        "  offset_from_utc, instance_number, instance_status,"
        "  auth_date_time, auth_comment, auth_cert_num)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            file_id,
            parms.get("sop_class"),
            parms.get("sop_instance"),
            parms.get("spec_char_set"),
            parms.get("creation_date"),
            parms.get("creation_time"),
            parms.get("creator_uid"),
            parms.get("related_general_sop_class"),
            # The Perl passes $parms{original_specialized_sop_class}, but
            # the value was read into the key 'orig_spec_sop_class', so this
            # column is unconditionally NULL. Confirmed against the dev
            # database: 0 of 1256 rows populated. Reproduced by default; see
            # posda.ingest.fixes.
            (
                parms.get("orig_spec_sop_class")
                if fixes.ACTIVE.original_specialized_sop_class
                else None
            ),
            parms.get("offset_from_utc"),
            parms.get("instance_number"),
            parms.get("instance_status"),
            parms.get("auth_date_time"),
            parms.get("auth_comment"),
            parms.get("auth_cert_num"),
        ],
    )


def _run_handlers(
    db: "Database",
    values: ParsedValues,
    file_id: int,
    sop_class: str | None,
    import_event_id: object,
    errors: list[str],
    registry: dict[str, object],
    rt_runner: object = None,
) -> None:
    entry = SOP_HANDLERS.get(sop_class) if sop_class is not None else None
    if entry is None:
        errors.append(f'No handlers (or name) for "{sop_class}"')
        return
    if not entry.handlers:
        errors.append(f"No handlers for {entry.name} ({sop_class})")
        return

    hist: dict = {"import_event_id": import_event_id}
    handlers = entry.handlers
    index = 0
    while index < len(handlers):
        name = handlers[index]

        # RT handlers are delegated to Perl as a contiguous block. They must
        # share one process: StructureSet builds nested hist entries that
        # RoiContour and RtRoiObservations consume, and those cannot survive
        # a round trip through the bridge.
        if name in RT_HANDLERS and rt_runner is not None:
            block = []
            while index < len(handlers) and handlers[index] in RT_HANDLERS:
                block.append(handlers[index])
                index += 1
            rt_runner(values, file_id, block, hist, errors)
            continue

        handler = registry.get(name)
        if handler is None:
            log.warning("No implementation registered for handler %s", name)
        else:
            handler(db, values, file_id, hist, errors)
        index += 1
