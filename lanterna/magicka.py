#!/usr/bin/python3 -u
USAGE="""\
Render MIP projections for review in Kaleidoscope.

By default, run in a loop and process all waiting IECs.

See optional arguments for more ways to run.

"""
import psycopg2
import tempfile
import os
import hashlib
from enum import Enum
from typing import Iterator, List
import time
import sys
import logging
import signal

import numpy as np
import pydicom
from PIL import Image

from pydicom.pixels import apply_color_lut, apply_modality_lut

import requests
import argparse


URL = os.environ.get("POSDA_INTERNAL_API_URL") + '/v1/import/'
DEBUG = True

# Panels are laid out at this size (each fit within, preserving aspect ratio)
# with this much padding, mirroring the old `montage -geometry 512x512+4+4`.
TILE_SIZE = 512
TILE_PADDING = 4

# Convert SIGTERM into an exception
class SigTerm(SystemExit): pass
def termhandler(a, b):
    raise SigTerm(1)
signal.signal(signal.SIGTERM, termhandler)

class ProjectionType(Enum):
    MIN = "min"
    AVG = "avg"
    MAX = "max"

def md5sum(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def add_file(filename: str) -> int:
    digest = md5sum(filename)
    with open(filename, "rb") as infile:
        r = requests.put(URL + "file", params={
            'digest': digest,
        }, data=infile)

        try:
            resp = r.json()
            return resp['file_id']
        except:
            logging.error(r.content)
            raise


def iter_display_frames(dcm_path: str) -> Iterator[np.ndarray]:
    """Yield each frame of a DICOM file as a float array whose values run
    dark-to-bright in *display* orientation.

    Grayscale frames come back 2-D; colour frames come back 3-D RGB (so the
    projection is done per channel, as the old ImageMagick pipeline did). For
    grayscale, the rescale slope/intercept (modality LUT) is applied and
    MONOCHROME1 is inverted so a higher value always means a brighter displayed
    pixel -- this keeps bright burned-in text bright in the projection. PALETTE
    COLOR frames are expanded through their lookup table (pydicom already hands
    back RGB for RGB/YBR pixel data).
    """
    ds = pydicom.dcmread(dcm_path)
    pixels = ds.pixel_array
    num_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
    photometric = getattr(ds, "PhotometricInterpretation", "")
    samples = int(getattr(ds, "SamplesPerPixel", 1) or 1)
    is_color = samples > 1 or "PALETTE" in photometric

    # a bare 3-D array is ambiguous (multi-frame grayscale vs single colour
    # frame), so key the frame split on NumberOfFrames, never on ndim
    frames = pixels if num_frames > 1 else pixels[np.newaxis, ...]
    for frame in frames:
        if is_color:
            yield to_rgb(frame, ds, photometric).astype(np.float64)
            continue
        arr = apply_modality_lut(frame, ds).astype(np.float64)
        if photometric == "MONOCHROME1":
            # only ordering matters (we min/max-window at the end), so a plain
            # negation flips MONOCHROME1 polarity without picking a max value
            arr = -arr
        yield arr


def to_rgb(frame: np.ndarray, ds, photometric: str) -> np.ndarray:
    """Return a colour frame as an (rows, cols, 3) RGB array.

    pydicom's ``pixel_array`` already converts YBR to RGB, so only PALETTE
    COLOR (handed back as raw indices) needs expanding through its LUT.
    """
    if "PALETTE" in photometric:
        return apply_color_lut(frame, ds)
    return frame  # RGB, or YBR already converted to RGB by pixel_array


class ProjectionAccumulator:
    """Compute MIP / MinIP / average projections in a single streaming pass.

    Only three image-sized accumulators are held at once (running max, min and
    sum), so peak memory is O(image area) regardless of how many slices or
    frames the series contains. The old code fed the whole decoded stack to
    ImageMagick's ``-maximum``/``-minimum``/``-average`` at once, which buffered
    every slice simultaneously and drove the OOM kills.
    """

    def __init__(self) -> None:
        self._max: np.ndarray | None = None
        self._min: np.ndarray | None = None
        self._sum: np.ndarray | None = None
        self._count = 0

    def add(self, frame: np.ndarray) -> None:
        if self._max is None:
            self._max = frame.copy()
            self._min = frame.copy()
            self._sum = frame.copy()
        else:
            if frame.shape != self._max.shape:
                raise ValueError(
                    f"frame shape {frame.shape} does not match series "
                    f"shape {self._max.shape}"
                )
            np.maximum(self._max, frame, out=self._max)
            np.minimum(self._min, frame, out=self._min)
            self._sum += frame
        self._count += 1

    def projection(self, projection_type: ProjectionType) -> np.ndarray:
        if self._count == 0:
            raise ValueError("no frames were accumulated")
        if projection_type is ProjectionType.MAX:
            return self._max
        if projection_type is ProjectionType.MIN:
            return self._min
        return self._sum / self._count


def to_8bit(projection: np.ndarray) -> np.ndarray:
    """Window a float projection to a 0-255 uint8 image via its own min/max.

    Per-panel windowing means the brightest value in the projection maps to
    pure white -- so a single bright burned-in-text pixel stands out sharply in
    the max projection.
    """
    low = float(projection.min())
    high = float(projection.max())
    if high <= low:
        return np.zeros(projection.shape, dtype=np.uint8)
    scaled = (projection - low) / (high - low) * 255.0
    return np.rint(scaled).astype(np.uint8)


def make_montage(panels: List[np.ndarray]) -> Image.Image:
    """Lay the given 8-bit panels out left-to-right into a single image.

    Panels are grayscale (2-D) or RGB (3-D); the montage matches.
    """
    mode = "RGB" if panels[0].ndim == 3 else "L"
    cell = TILE_SIZE + 2 * TILE_PADDING
    canvas = Image.new(mode, (cell * len(panels), cell), color=0)
    for index, panel in enumerate(panels):
        tile = Image.fromarray(panel)  # mode inferred from shape/dtype
        tile.thumbnail((TILE_SIZE, TILE_SIZE))  # fit within, keep aspect ratio
        x = index * cell + TILE_PADDING + (TILE_SIZE - tile.width) // 2
        y = TILE_PADDING + (TILE_SIZE - tile.height) // 2
        canvas.paste(tile, (x, y))
    return canvas


def render_projection_from_filelist(files: List[str]) -> str:
    """Render a full projection montage from the given list of files.

    Returns the filename to the output image, which must be manually
    deleted after use.
    """
    accumulator = ProjectionAccumulator()
    for index, filename in enumerate(files):
        logging.debug(f"{index}: {filename}")
        for frame in iter_display_frames(filename):
            accumulator.add(frame)

    # order matches the old montage: max, then average, then min
    panels = [
        to_8bit(accumulator.projection(ProjectionType.MAX)),
        to_8bit(accumulator.projection(ProjectionType.AVG)),
        to_8bit(accumulator.projection(ProjectionType.MIN)),
    ]

    output_filename = tempfile.mktemp(suffix='.jpg')
    make_montage(panels).save(output_filename, "JPEG")
    return output_filename


def render_projection(cursor, iec: int) -> None:
    """Render a projection of the given IEC

    This method follows these steps:
    * build a filelist of all input files for the IEC
    * decode each input image and accumulate min/max/avg projections
    * generate a final montage
    """

    logging.info(f"Rendering projection for IEC: {iec}.")
    # look up the input files
    cursor.execute("""
        select root_path || '/' || rel_path as path, number_of_frames
        from image_equivalence_class_input_image
        natural join file_location
        natural join file_storage_root
        natural join file_image
        natural join image
        where image_equivalence_class_id = %s
    """, [iec])

    # get their paths and assemble into a filelist (multi-frame files are
    # expanded frame-by-frame while decoding)
    files = [path for path, _number_of_frames in cursor]
    logging.info(f"Found {len(files)} images in this IEC.")

    projection_filename = render_projection_from_filelist(files)

    try:
        # import final file into posda and get file_id
        file_id = add_file(projection_filename)
        logging.debug(f"file_id: {file_id}")

        # insert row into output_image table
        cursor.execute("""
            insert into image_equivalence_class_out_image
            values (%s, 'combined', %s)
        """, [iec, file_id])

        # update iec table to ReadyToReview
        cursor.execute("""
            update image_equivalence_class
            set processing_status = 'ReadyToReview'
            where image_equivalence_class_id = %s
        """, [iec])
    finally:
        os.unlink(projection_filename)

def get_iecs_in_visual_review(cursor, visual_review_id: int) -> List[int]:
    cursor.execute("""
        select image_equivalence_class_id
        from image_equivalence_class
        where visual_review_instance_id = %s
    """, [visual_review_id])

    return [iec for iec, in cursor]

def process_single_vr(visual_review_instance_id: int) -> None:
    conn = connect()
    cur = conn.cursor()


    iecs = get_iecs_in_visual_review(cur, visual_review_instance_id)
    logging.info(f"Found {len(iecs)} IECs in visual review {visual_review_instance_id}.")
    if len(iecs) > 0:
        logging.info("Rendering projections...")

    for iec in iecs:
        try:
            render_projection(cur, iec)
        except Exception as e:
            log_error(cur, iec, e)

    conn.close()

def connect():
    conn = psycopg2.connect("dbname=posda_files")
    conn.autocommit = True
    # cur = conn.cursor()

    return conn


def log_error(cur, iec: int, e: Exception):
    logging.error(f"Magicka ERROR: IEC {iec} failed, err is: {e}")
    query = """
        update image_equivalence_class i
        set processing_status = 'error'
        where i.image_equivalence_class_id = %s
    """
    cur.execute(query, [iec])


def process_all_unprocessed():
    conn = connect()
    cur = conn.cursor()

    query = """
        update image_equivalence_class i
        set processing_status = 'in-progress'
        where i.image_equivalence_class_id in (
          select image_equivalence_class_id
          from image_equivalence_class
          where processing_status = 'ReadyToProcess'
          limit 1
          for update skip locked
        )
        returning i.*
    """

    while True:
        cur.execute(query)
        row = cur.fetchone()
        if row is None:
            time.sleep(5)  # sleep 5 seconds
            continue

        iec, *rest = row
        try:
            render_projection(cur, iec)
        except Exception as e:
            log_error(cur, iec, e)

def parse_args():
    parser = argparse.ArgumentParser(description=USAGE)
    parser.add_argument('--vr', help='a visual_review_instance_id to run for')
    parser.add_argument('--iec', help='an IEC to run for')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='be extremely verbose'
    )

    return parser.parse_args()

def main(args) -> None:
    if args.vr is not None:
        logging.info(f"Processing a single VR: {args.vr}")
        process_single_vr(args.vr)
    elif args.iec is not None:
        logging.info(f"Processing a single IEC: {args.iec}")
        cur = connect().cursor()
        render_projection(cur, args.iec)
    else:
        logging.info("Processing all unprocessed IECs...")
        process_all_unprocessed()

def configure_logging(args):
    """Setup sane default logging settings"""
    if args.debug:
        format = "%(levelname)s:%(asctime)s:%(lineno)s:%(funcName)s:%(message)s"

        logging.basicConfig(level=logging.DEBUG,
                            format=format,
                            datefmt='%Y-%m-%d/%H:%M:%S')

    else:
        logging.basicConfig(level=logging.INFO,
                            format="%(message)s")

if __name__ == '__main__':
    args = parse_args()
    configure_logging(args)
    main(args)
