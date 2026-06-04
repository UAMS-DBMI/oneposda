#!/usr/bin/env python3
"""
Fix RT and SEG structural linkages by rewriting DICOM files to reference
the correct target series.

Reads a Relink_Worklist CSV from stdin (header: file_id,target_series_instance_uid).
Supported modalities: RTSTRUCT (full series relink), SEG (ReferencedSeriesSequence rewrite).

Fixed files are written to $POSDA_CACHE_ROOT/edits/<uuid>/ for review before import.
"""
import sys
import os
import csv
import uuid
import hashlib
import subprocess
import argparse
import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence as DicomSequence
from posda.database import Database
from posda.background.process import BackgroundProcess

DIVIDER = "------------------------------------------"


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

def _query_series_sops(conn, series_uid, activity_id):
    """Return {sop_uid: {for_uid, study_uid, sop_class}} for the series in this activity."""
    cur = conn.cursor()
    cur.execute("""
        SELECT fsc.sop_instance_uid, ff.for_uid, fst.study_instance_uid,
               fm.media_storage_sop_class
        FROM file_series fser
        JOIN activity_timepoint_file atf ON atf.file_id = fser.file_id
        JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
        JOIN file_sop_common fsc ON fsc.file_id = fser.file_id
        LEFT JOIN file_for ff ON ff.file_id = fser.file_id
        LEFT JOIN file_study fst ON fst.file_id = fser.file_id
        LEFT JOIN file_meta fm ON fm.file_id = fser.file_id
        WHERE fser.series_instance_uid = %s
          AND at.activity_id = %s
    """, (series_uid, activity_id))
    result = {}
    for sop, for_uid, study, sop_class in cur.fetchall():
        if sop:
            result[sop] = {'for_uid': for_uid, 'study_uid': study, 'sop_class': sop_class or ''}
    cur.close()
    return result


# ------------------------------------------------------------------
# pydicom helpers
# ------------------------------------------------------------------

def _ref_seq(series_sops):
    """Sequence of (ReferencedSOPClassUID, ReferencedSOPInstanceUID) items."""
    items = []
    for sop, info in series_sops.items():
        item = Dataset()
        item.ReferencedSOPClassUID = info['sop_class']
        item.ReferencedSOPInstanceUID = sop
        items.append(item)
    return DicomSequence(items)


def _build_sop_map(old_sops, series_sops):
    """
    Map old contour SOP UIDs to SOPs in the target series.

    SOPs already present in the target series map to themselves (FOR-only mismatch).
    Remaining old SOPs fall back to sorted positional mapping against remaining new SOPs.
    """
    sop_map = {}
    unmapped_old = []
    for old in old_sops:
        if old in series_sops:
            sop_map[old] = old
        else:
            unmapped_old.append(old)
    unmapped_new = [s for s in sorted(series_sops) if s not in sop_map.values()]
    for i, old in enumerate(sorted(unmapped_old)):
        if i < len(unmapped_new):
            sop_map[old] = unmapped_new[i]
    return sop_map


# ------------------------------------------------------------------
# Modality-specific fixers
# ------------------------------------------------------------------

def fix_rtstruct(ds, target_series_uid, series_sops):
    """
    Relink RTSTRUCT to target_series_uid (Python port of Posda::StructFixer).

    Updates ReferencedFrameOfReferenceSequence (FOR, study, series, SOP list)
    and patches ROIContourSequence contour image SOP references via _build_sop_map.

    Returns (success: bool, errors: list[str]).
    """
    if not series_sops:
        return False, ["No SOPs found in target series for this activity"]

    sample    = next(iter(series_sops.values()))
    new_for   = sample['for_uid']
    new_study = sample['study_uid']
    if not new_for or not new_study:
        return False, ["Target series missing FOR or Study UID"]

    old_sops = {
        img.ReferencedSOPInstanceUID
        for roi     in getattr(ds,  'ROIContourSequence', [])
        for contour in getattr(roi, 'ContourSequence',    [])
        for img     in getattr(contour, 'ContourImageSequence', [])
        if hasattr(img, 'ReferencedSOPInstanceUID')
    }
    sop_map = _build_sop_map(old_sops, series_sops)
    errors  = [f"Unmapped contour SOP: {s}" for s in old_sops - set(sop_map)]

    for for_item in getattr(ds, 'ReferencedFrameOfReferenceSequence', []):
        for_item.FrameOfReferenceUID = new_for
        for study_item in getattr(for_item, 'RTReferencedStudySequence', []):
            study_item.ReferencedSOPInstanceUID = new_study
            for series_item in getattr(study_item, 'RTReferencedSeriesSequence', []):
                series_item.SeriesInstanceUID = target_series_uid
                series_item.ContourImageSequence = _ref_seq(series_sops)

    for roi in getattr(ds, 'ROIContourSequence', []):
        for contour in getattr(roi, 'ContourSequence', []):
            for img in getattr(contour, 'ContourImageSequence', []):
                old = getattr(img, 'ReferencedSOPInstanceUID', None)
                if old and old in sop_map:
                    new = sop_map[old]
                    img.ReferencedSOPInstanceUID = new
                    img.ReferencedSOPClassUID    = series_sops[new]['sop_class']

    return True, errors


def fix_seg(ds, target_series_uid, series_sops):
    """
    Rewrite SEG ReferencedSeriesSequence to point at target_series_uid,
    rebuilding ReferencedInstanceSequence from the target series SOPs.

    Returns (success: bool, errors: list[str]).
    """
    if not series_sops:
        return False, ["No SOPs found in target series for this activity"]
    if not hasattr(ds, 'ReferencedSeriesSequence'):
        return False, ["SEG has no ReferencedSeriesSequence"]

    for series_item in ds.ReferencedSeriesSequence:
        series_item.SeriesInstanceUID = target_series_uid
        series_item.ReferencedInstanceSequence = _ref_seq(series_sops)

    return True, []


# ------------------------------------------------------------------
# Diff helper
# ------------------------------------------------------------------

def _file_digest(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _run_compare(orig_path, new_path):
    """Run ShortLongDicomCompare.pl; return (short_text, long_text) or ('', '')."""
    try:
        result = subprocess.run(
            ['ShortLongDicomCompare.pl', orig_path, new_path],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return '', ''
    short, long_, mode = '', '', None
    for line in result.stdout.splitlines():
        if line == 'short_rept:':
            mode = 'short'
        elif line == 'long_rept:':
            mode = 'long'
        elif line.startswith('---'):
            mode = None
        elif mode == 'short':
            short += line + '\n'
        elif mode == 'long':
            long_ += line + '\n'
    return short, long_


# ------------------------------------------------------------------
# Main runner
# ------------------------------------------------------------------

_FIXERS = {
    'RTSTRUCT': fix_rtstruct,
    'SEG':      fix_seg,
}


def run(args, background, conn):
    print(DIVIDER)
    print("FixLinkages.py running:")
    print(f"  Activity: {args.activity_id}")
    print(f"  Comment:  {args.comment}")
    print(DIVIDER)

    reader   = csv.DictReader(sys.stdin)
    worklist = [
        {'file_id':          int(row['file_id']),
         'target_series_uid': row['target_series_instance_uid']}
        for row in reader
    ]
    if not worklist:
        print("Empty worklist — nothing to do.")
        background.finish("No items")
        return

    dest_dir = os.path.join(
        os.environ.get('POSDA_CACHE_ROOT', '/tmp'), 'edits', str(uuid.uuid4())
    )
    os.makedirs(dest_dir, exist_ok=True)
    print(f"Output directory: {dest_dir}")
    print(f"Processing {len(worklist)} item(s)")

    fix_rpt    = background.create_report("LinkageFixReport")
    fix_writer = csv.writer(fix_rpt, lineterminator='\n')
    fix_writer.writerow(["file_id", "modality", "target_series_uid",
                          "dest_file", "status", "errors"])

    diff_rpt    = background.create_report("DiffReport")
    diff_writer = csv.writer(diff_rpt, lineterminator='\n')
    diff_writer.writerow(["file_id", "modality", "from_digest", "to_digest",
                           "short_diff", "long_diff"])

    num_ok = num_bad = num_skip = 0

    for i, item in enumerate(worklist, 1):
        file_id       = item['file_id']
        target_series = item['target_series_uid']
        background.set_activity_status(f"Fixing {file_id} ({i}/{len(worklist)})")

        cur = conn.cursor()
        cur.execute("""
            SELECT storage_path(f.file_id), fm.modality, fsc.sop_instance_uid
            FROM file f
            LEFT JOIN file_meta fm ON fm.file_id = f.file_id
            LEFT JOIN file_sop_common fsc ON fsc.file_id = f.file_id
            WHERE f.file_id = %s
        """, (file_id,))
        file_row = cur.fetchone()
        cur.close()

        if not file_row:
            fix_writer.writerow([file_id, '', target_series, '', 'Failed', 'File not found'])
            num_bad += 1
            continue

        orig_path, modality, sop_uid = file_row
        fixer = _FIXERS.get(modality)

        if fixer is None:
            fix_writer.writerow([file_id, modality, target_series, '',
                                  'Skipped', f"Modality {modality} not supported"])
            num_skip += 1
            continue

        try:
            ds = pydicom.dcmread(orig_path, force=True)
        except Exception as e:
            fix_writer.writerow([file_id, modality, target_series, '', 'Failed', str(e)])
            num_bad += 1
            continue

        series_sops       = _query_series_sops(conn, target_series, args.activity_id)
        dest_file         = os.path.join(dest_dir, f"{modality}_{sop_uid}.dcm")
        success, errors   = fixer(ds, target_series, series_sops)

        if not success:
            fix_writer.writerow([file_id, modality, target_series, '',
                                  'Failed', '; '.join(errors)])
            num_bad += 1
            continue

        try:
            ds.save_as(dest_file)
        except Exception as e:
            fix_writer.writerow([file_id, modality, target_series, '',
                                  'Failed', f"Write error: {e}"])
            num_bad += 1
            continue

        from_dig        = _file_digest(orig_path)
        to_dig          = _file_digest(dest_file)
        short, long_    = _run_compare(orig_path, dest_file)
        diff_writer.writerow([file_id, modality, from_dig, to_dig, short, long_])

        fix_writer.writerow([file_id, modality, target_series, dest_file,
                              'OK', '; '.join(errors)])
        num_ok += 1

    print(DIVIDER)
    print(f"Results: {num_ok} OK, {num_bad} Failed, {num_skip} Skipped")
    print(f"Fixed files in: {dest_dir}")

    background.insert_email_button(
        "Reject Edits and Delete Temporary Files",
        "ScriptButton",
        {
            "op":                   "OpenTableFreePopup",
            "class_":               "Posda::NewerProcessPopup",
            "cap_":                 "RejectEditsTp",
            "subprocess_invoc_id":  args.background_id,
            "notify":               args.notify,
        },
    )
    background.insert_email_button(
        "Accept Edits, Import and Delete Temporary Files",
        "ScriptButton",
        {
            "op":                   "OpenTableFreePopup",
            "class_":               "Posda::NewerProcessPopup",
            "cap_":                 "ImportEditsTp",
            "subprocess_invoc_id":  args.background_id,
            "notify":               args.notify,
        },
    )

    background.finish(f"Complete: {num_ok} OK, {num_bad} Failed, {num_skip} Skipped")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('background_id', help='background_subprocess_id')
    parser.add_argument('activity_id',   help='activity to fix against')
    parser.add_argument('comment',       help='description of this fix run')
    parser.add_argument('notify',        help='user to notify when complete')
    return parser.parse_args()


def main(args):
    background = BackgroundProcess(args.background_id, args.notify, args.activity_id)
    background.daemonize()
    conn = Database("posda_files")
    try:
        run(args, background, conn)
    except Exception as e:
        print("FATAL ERROR:", e)
        background.finish("Failed")
        raise


if __name__ == '__main__':
    main(parse_args())
