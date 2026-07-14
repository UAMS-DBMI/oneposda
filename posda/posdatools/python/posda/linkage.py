#!/usr/bin/env python3
import csv
import os
import pydicom
import requests
from collections import defaultdict
from io import BytesIO
from posda.config import Config
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

DIVIDER = "------------------------------------------"
TCIA_UID_ROOT = "<!1.3.6.1.4.1.14519.5.2.1>"

TAGS_TO_SCAN = [
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "ReferencedSOPInstanceUID",
    "MultiFrameSourceSOPInstanceUID",
    "SOPInstanceUIDOfConcatenationSource",
    "FrameOfReferenceUID",
]
UID_KEYWORDS = set(TAGS_TO_SCAN)

REFERENCE_SEQUENCES_SEG = frozenset({
    "ReferencedSeriesSequence",        # series UID + image SOP UIDs
})

REFERENCE_SEQUENCES_RT = frozenset({
    "ReferencedFrameOfReferenceSequence",  # RTSTRUCT → image series/SOPs
    "ROIContourSequence",                  # RTSTRUCT → image SOPs (per-contour)
    "ReferencedStructureSetSequence",      # RTPLAN/RTDOSE → RTSTRUCT SOP
    "ReferencedRTPlanSequence",            # RTDOSE/RTIMAGE → RTPLAN SOP
    "ReferencedDoseSequence",              # RTPLAN → RTDOSE SOP
    "RelatedRTPlanSequence",               # RTPLAN → related plan SOPs
})

REFERENCE_REPORT_HEADER = [
    "file_id", "modality", "series_instance_uid", "path", "key_path",
    "category", "referenced_uid", "referenced_sop_class", "missing",
    "found_activity_id", "found_timepoint_id", "found_file_id", "note",
    "candidate_series_uid", "candidate_modality", "candidate_confidence", "candidate_note",
]

FOR_MISMATCH_HEADER = [
    "file_id", "modality", "series_instance_uid", "study_instance_uid", "path", "key_path",
    "referenced_uid", "referenced_sop_class", "referenced_series_uid",
    "file_for_uid", "referenced_for_uid",
    "candidate_series_uid", "candidate_modality", "candidate_confidence", "all_candidates",
    "fix_direction",
]


def walk_dataset(ds, depth=0, path=None, key_path=None, reference_sequences=None):
    """Traverse a pydicom Dataset recursively, yielding (depth, elem, path, key_path).

    If reference_sequences is given, top-level (depth 0) elements whose keyword isn't in
    that set are skipped without recursing into them, so large irrelevant sequences (e.g.
    SegmentSequence, ROIContourSequence) aren't walked when the caller only cares about a
    handful of named top-level reference sequences.
    """
    if path is None:
        path = []
    if key_path is None:
        key_path = []
    for elem in ds:
        if depth == 0 and reference_sequences is not None and elem.keyword not in reference_sequences:
            continue
        tag_hex = f"({elem.tag.group:04X},{elem.tag.element:04X})"
        keyword = elem.keyword if elem.keyword else tag_hex
        current_path = path + [tag_hex]
        current_key_path = key_path + [keyword]
        if isinstance(elem.value, Sequence):
            for i, item in enumerate(elem.value):
                seq_path = current_path + [f"[{i}]"]
                seq_key_path = current_key_path + ["|"]
                yield from walk_dataset(item, depth + 1, seq_path, seq_key_path, reference_sequences)
        elif isinstance(elem.value, Dataset):
            yield from walk_dataset(elem.value, depth + 1, current_path, current_key_path, reference_sequences)
        elif elem.tag == (0x7FE0, 0x0010):
            continue
        else:
            yield depth, elem, current_path, current_key_path


def walk_dataset_for_referencing(ds, reference_sequences=None):
    """Walk dataset at depth > 0, yielding UID_KEYWORDS tags and ReferencedSOPClassUID.

    ReferencedSOPClassUID is yielded alongside SOP instance UIDs so callers can
    correlate them by shared parent key_path to determine the expected SOP class
    for each reference. reference_sequences, if given, restricts which top-level
    sequences are walked at all (see walk_dataset).
    """
    for depth, elem, path, key_path in walk_dataset(ds, reference_sequences=reference_sequences):
        if depth > 0 and (elem.keyword in UID_KEYWORDS or
                          elem.keyword == 'ReferencedSOPClassUID'):
            yield depth, elem, path, key_path


def reference_to_row(entry):
    return (
        entry["file_id"],
        entry["modality"],
        entry["series_instance_uid"],
        entry["path"],
        entry["key_path"],
        entry["category"],
        entry["uid"],
        entry.get("referenced_sop_class", ""),
        "X" if entry.get("missing") else "",
        entry.get("found_activity_id", ""),
        entry.get("found_timepoint_id", ""),
        entry.get("found_file_id", ""),
        entry.get("note", ""),
        entry.get("candidate_series_uid", ""),
        entry.get("candidate_modality", ""),
        entry.get("candidate_confidence", ""),
        entry.get("candidate_note", ""),
    )


class LinkageChecker:
    """
    Base class for DICOM linkage checking scripts.

    Subclasses call run() and override load_dataset() for non-disk file sources.
    Modality-specific checks extend find_missing_references() or add their own methods.

    Standard dict shapes:
      missing_ref:   file_id, modality, series_instance_uid, path, key_path,
                     uid, category, note, missing, [found_activity_id, found_timepoint_id]
      for_mismatch:  file_id, modality, series_instance_uid, path, key_path,
                     referenced_uid, referenced_series_uid, file_for_uid, referenced_for_uid
      relink_item:   file_id, target_series_uid
    """

    # Set to a frozenset of top-level sequence names to restrict reference scanning.
    # None (default) scans all nested UID tags; subclasses override for SEG/RT.
    reference_sequences = None

    def __init__(self, args, background, conn):
        self.args = args
        self.background = background
        self.conn = conn

    # ------------------------------------------------------------------
    # File fetching
    # ------------------------------------------------------------------

    def get_activity_files(self, modality_filter=None):
        """Return all DICOM file rows for the latest activity timepoint.

        modality_filter may be a single string (e.g. 'SEG') or a list
        (e.g. ['RTSTRUCT', 'RTPLAN', 'RTDOSE', 'RTIMAGE']).
        Omit to retrieve all modalities for building the UID context.
        """
        if modality_filter is None:
            modality_clause = ""
            params = (self.args.activity_id,)
        elif isinstance(modality_filter, (list, tuple)):
            modality_clause = "WHERE fs.modality = ANY(%s)"
            params = (self.args.activity_id, list(modality_filter))
        else:
            modality_clause = "WHERE fs.modality = %s"
            params = (self.args.activity_id, modality_filter)
        cur = self.conn.cursor()
        cur.execute(f"""
            WITH files_in_activity AS (
                SELECT atf.file_id, at.activity_id, at.activity_timepoint_id
                FROM activity_timepoint_file atf
                JOIN file f ON f.file_id = atf.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE atf.activity_timepoint_id = (
                    SELECT MAX(activity_timepoint_id)
                    FROM activity_timepoint
                    WHERE activity_id = %s
                )
                AND f.is_dicom_file = true
            )
            SELECT
                fia.file_id,
                fia.activity_id,
                fia.activity_timepoint_id,
                storage_path(fia.file_id)  AS storage_path,
                fm.media_storage_sop_class,
                fs.modality,
                fsc.sop_instance_uid,
                fs.series_instance_uid,
                fst.study_instance_uid,
                fp.patient_id,
                ff.for_uid
            FROM files_in_activity fia
            LEFT JOIN file_meta        fm  ON fm.file_id  = fia.file_id
            LEFT JOIN file_sop_common  fsc ON fsc.file_id = fia.file_id
            LEFT JOIN file_series      fs  ON fs.file_id  = fia.file_id
            LEFT JOIN file_study       fst ON fst.file_id = fia.file_id
            LEFT JOIN file_patient     fp  ON fp.file_id  = fia.file_id
            LEFT JOIN file_for         ff  ON ff.file_id  = fia.file_id
            {modality_clause}
        """, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    def get_file_data(self, file_id):
        """Fetch raw file bytes via the internal API."""
        resp, _, success = self.call_api(f'/files/{file_id}/data', 0)
        return resp.content if success else None

    def load_dataset(self, file_record):
        """Load a pydicom Dataset from a file record.

        When POSDA_API_ONLY is set, fetches content via the internal API
        instead of reading from disk (useful for local testing environments).
        """
        if os.getenv('POSDA_API_ONLY'):
            content = self.get_file_data(file_record.file_id)
            if not content:
                return None
            return pydicom.dcmread(BytesIO(content), stop_before_pixels=True, force=True)
        return pydicom.dcmread(file_record.storage_path, stop_before_pixels=True, force=True)

    # ------------------------------------------------------------------
    # UID context
    # ------------------------------------------------------------------

    def build_uid_context(self, file_rows):
        """Build UID lookup sets from a list of file rows.

        Returns: (sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series)
        sop_to_for / sop_to_series map a SOP UID to the FOR / series of the file that owns it.
        """
        sop_uids = set()
        series_uids = set()
        study_uids = set()
        for_uids = set()
        sop_to_for = {}
        sop_to_series = {}
        sop_to_file_id = {}
        for row in file_rows:
            sop    = row.sop_instance_uid
            series = row.series_instance_uid
            study  = row.study_instance_uid
            for_uid = row.for_uid
            if sop:
                sop_uids.add(sop)
                if for_uid:
                    sop_to_for[sop] = for_uid
                if series:
                    sop_to_series[sop] = series
                sop_to_file_id[sop] = row.file_id
            if series:
                series_uids.add(series)
            if study:
                study_uids.add(study)
            if for_uid:
                for_uids.add(for_uid)
        return sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series, sop_to_file_id

    # ------------------------------------------------------------------
    # Reference scanning
    # ------------------------------------------------------------------

    def find_missing_references(
        self, file_rows, sop_uids, series_uids, study_uids, for_uids, sop_to_for, sop_to_series,
        sop_to_file_id=None,
    ):
        """Walk each file's DICOM dataset and collect reference anomalies.

        Returns: (missing_references, for_mismatches)
        """
        missing_references = []
        for_mismatches = []
        for i, file in enumerate(file_rows):
            try:
                ds = self.load_dataset(file)
            except Exception as e:
                print(f"  Warning: could not load file {file.file_id}: {e}")
                continue
            if ds is None:
                continue

            sop_class_context = {}  # tuple(parent_key_path) → ReferencedSOPClassUID

            for _, elem, path, key_path in walk_dataset_for_referencing(ds, self.reference_sequences):
                val = getattr(elem, 'value', None)
                if not isinstance(val, str):
                    continue

                # Track SOP class so it can be paired with the next SOP instance UID
                # in the same sequence item (same parent key_path).
                if elem.keyword == 'ReferencedSOPClassUID':
                    sop_class_context[tuple(key_path[:-1])] = val
                    continue

                exists = False
                category = None

                if key_path[0] == "ReferencedStudySequence" and len(key_path) > 2 and key_path[2] == "ReferencedSOPInstanceUID":
                    category = "study"
                    exists = val in study_uids
                elif len(key_path) > 4 and key_path[2] == "RTReferencedStudySequence" and key_path[4] == "ReferencedSOPInstanceUID":
                    category = "study"
                    exists = val in study_uids
                elif elem.keyword in ("ReferencedSOPInstanceUID", "SOPInstanceUID",
                                      "MultiFrameSourceSOPInstanceUID",
                                      "SOPInstanceUIDOfConcatenationSource"):
                    category = "sop"
                    exists = val in sop_uids
                elif elem.keyword == "SeriesInstanceUID":
                    category = "series"
                    exists = val in series_uids
                elif elem.keyword == "StudyInstanceUID":
                    category = "study"
                    exists = val in study_uids
                elif elem.keyword == "FrameOfReferenceUID":
                    category = "for"
                    exists = val in for_uids

                if category:
                    ref_sop_class = (
                        sop_class_context.get(tuple(key_path[:-1]))
                        if category == "sop" else None
                    )
                    entry = {
                        "file_id":              file.file_id,
                        "modality":             file.modality,
                        "series_instance_uid":  file.series_instance_uid,
                        "study_instance_uid":   file.study_instance_uid,
                        "file_for_uid":         file.for_uid,
                        "patient_id":           file.patient_id,
                        "path":                 f"<{''.join(path)}>",
                        "key_path":             f"<{''.join(key_path)}>",
                        "uid":                  val,
                        "category":             category,
                        "referenced_sop_class": ref_sop_class,
                        "note":                 "",
                        "missing":              not exists,
                    }
                    if exists:
                        entry["found_activity_id"]   = file.activity_id
                        entry["found_timepoint_id"]  = file.activity_timepoint_id
                        if category == "sop" and sop_to_file_id:
                            entry["found_file_id"] = sop_to_file_id.get(val)
                    missing_references.append(entry)
                    if exists and category == "sop":
                        ref_for  = sop_to_for.get(val)
                        file_for = file.for_uid
                        if ref_for and file_for and ref_for != file_for:
                            for_mismatches.append({
                                "file_id":             file.file_id,
                                "modality":            file.modality,
                                "series_instance_uid": file.series_instance_uid,
                                "study_instance_uid":  file.study_instance_uid,
                                "path":                f"<{''.join(path)}>",
                                "key_path":            f"<{''.join(key_path)}>",
                                "referenced_uid":      val,
                                "referenced_series_uid": sop_to_series.get(val),
                                "file_for_uid":        file_for,
                                "referenced_for_uid":  ref_for,
                                "referenced_sop_class": ref_sop_class,
                            })

            if i and i % 100 == 0:
                print(f"  Scanned {i} files; "
                      f"total refs scanned: {len(missing_references)}, "
                      f"FOR mismatches so far: {len(for_mismatches)}")

        return missing_references, for_mismatches

    # ------------------------------------------------------------------
    # Global UID lookup and annotation
    # ------------------------------------------------------------------

    def lookup_uids_globally(self, category, uid_values):
        """Find the most recent activity/timepoint for UIDs across all of Posda."""
        if not uid_values:
            return {}
        queries = {
            "sop": """
                SELECT DISTINCT ON (fsc.sop_instance_uid)
                    fsc.sop_instance_uid, at.activity_id, at.activity_timepoint_id, atf.file_id
                FROM file_sop_common fsc
                JOIN activity_timepoint_file atf ON atf.file_id = fsc.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fsc.sop_instance_uid = ANY(%s)
                ORDER BY fsc.sop_instance_uid, at.activity_id DESC, at.activity_timepoint_id DESC
            """,
            "series": """
                SELECT DISTINCT ON (fs.series_instance_uid)
                    fs.series_instance_uid, at.activity_id, at.activity_timepoint_id, atf.file_id
                FROM file_series fs
                JOIN activity_timepoint_file atf ON atf.file_id = fs.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fs.series_instance_uid = ANY(%s)
                ORDER BY fs.series_instance_uid, at.activity_id DESC, at.activity_timepoint_id DESC
            """,
            "study": """
                SELECT DISTINCT ON (fst.study_instance_uid)
                    fst.study_instance_uid, at.activity_id, at.activity_timepoint_id, atf.file_id
                FROM file_study fst
                JOIN activity_timepoint_file atf ON atf.file_id = fst.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fst.study_instance_uid = ANY(%s)
                ORDER BY fst.study_instance_uid, at.activity_id DESC, at.activity_timepoint_id DESC
            """,
            "for": """
                SELECT DISTINCT ON (ff.for_uid)
                    ff.for_uid, at.activity_id, at.activity_timepoint_id, atf.file_id
                FROM file_for ff
                JOIN activity_timepoint_file atf ON atf.file_id = ff.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE ff.for_uid = ANY(%s)
                ORDER BY ff.for_uid, at.activity_id DESC, at.activity_timepoint_id DESC
            """,
        }
        query = queries.get(category)
        if not query:
            return {}
        cur = self.conn.cursor()
        cur.execute(query, (list(uid_values),))
        result = {
            row[0]: {'activity_id': row[1], 'activity_timepoint_id': row[2], 'file_id': row[3]}
            for row in cur.fetchall()
        }
        cur.close()
        return result

    def annotate_missing_refs(self, missing_refs):
        """Look up entries globally; set missing, found_activity_id, found_timepoint_id.

        Entries already marked missing=False are left untouched.
        """
        if not missing_refs:
            return missing_refs
        by_category = defaultdict(set)
        for entry in missing_refs:
            if entry.get("missing") is False:
                continue
            by_category[entry["category"]].add(entry["uid"])
        location_map = {}
        for category, uids in by_category.items():
            for uid_val, loc in self.lookup_uids_globally(category, uids).items():
                location_map[(category, uid_val)] = loc
        for entry in missing_refs:
            if entry.get("missing") is False:
                continue
            loc = location_map.get((entry["category"], entry["uid"]))
            if loc:
                entry["found_activity_id"]    = loc["activity_id"]
                entry["found_timepoint_id"]   = loc["activity_timepoint_id"]
                entry["found_file_id"]        = loc["file_id"]
                entry["missing"]              = False
            else:
                entry["missing"] = True
        return missing_refs

    # ------------------------------------------------------------------
    # API helper (used by subclasses that need HTTP calls)
    # ------------------------------------------------------------------

    def call_api(self, endpoint, call_type=0):
        """Generic HTTP helper; endpoint is the full path after /v1."""
        url = f'{Config.get("internal-api-url")}/v1{endpoint}'
        headers = {'Authorization': f'Bearer {Config.get("api_system_token")}'}
        try:
            if call_type == 0:
                response = requests.get(url, headers=headers)
            elif call_type == 1:
                response = requests.patch(url, headers=headers)
            elif call_type == 2:
                response = requests.put(url, headers=headers)
            if response.status_code == 200:
                return response, url, True
            print(f'Bad response: {response.status_code} - {response.text}')
        except Exception as e:
            print(f'Error processing request: {e}')
        return None, url, False

    # ------------------------------------------------------------------
    # Candidate series suggestion
    # ------------------------------------------------------------------

    def suggest_relink_candidates(self, for_mismatches):
        """Annotate FOR mismatches with candidate series that share the referencing file's FOR.

        Searches same study first (high confidence), then the current activity (lower
        confidence). Excludes the referencing file's own series and the already-referenced
        series from candidates.

        Adds to each mismatch dict:
          candidate_series_uid, candidate_modality, candidate_confidence, all_candidates
        """
        if not for_mismatches:
            return for_mismatches

        # Batch same-study lookup: series carrying file_for_uid within the same study.
        study_uids = list({m["study_instance_uid"] for m in for_mismatches
                           if m.get("study_instance_uid")})
        for_uids   = list({m["file_for_uid"] for m in for_mismatches
                           if m.get("file_for_uid")})

        # (for_uid, study_uid) → [(series_uid, modality, sop_class)]
        same_study_map = defaultdict(list)
        if study_uids and for_uids:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT ff.for_uid, fst.study_instance_uid,
                                fs.series_instance_uid, fs.modality,
                                fsc.sop_class_uid
                FROM file_for ff
                JOIN file_series    fs   ON fs.file_id   = ff.file_id
                JOIN file_study     fst  ON fst.file_id  = ff.file_id
                LEFT JOIN file_sop_common fsc ON fsc.file_id = ff.file_id
                WHERE ff.for_uid              = ANY(%s)
                  AND fst.study_instance_uid  = ANY(%s)
            """, (for_uids, study_uids))
            for row in cur.fetchall():
                same_study_map[(row[0], row[1])].append((row[2], row[3] or '', row[4] or ''))
            cur.close()

        # for_uid → [(series_uid, modality, sop_class)]
        activity_map = defaultdict(list)
        needs_activity = [
            m for m in for_mismatches
            if not same_study_map.get((m.get("file_for_uid"), m.get("study_instance_uid")))
        ]
        if needs_activity:
            fallback_fors = list({m["file_for_uid"] for m in needs_activity
                                   if m.get("file_for_uid")})
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT ff.for_uid, fs.series_instance_uid, fs.modality,
                                fsc.sop_class_uid
                FROM file_for ff
                JOIN file_series    fs   ON fs.file_id   = ff.file_id
                LEFT JOIN file_sop_common fsc ON fsc.file_id = ff.file_id
                JOIN activity_timepoint_file atf ON atf.file_id = ff.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE ff.for_uid    = ANY(%s)
                  AND at.activity_id = %s
            """, (fallback_fors, self.args.activity_id))
            for row in cur.fetchall():
                activity_map[row[0]].append((row[1], row[2] or '', row[3] or ''))
            cur.close()

        for m in for_mismatches:
            file_for    = m.get("file_for_uid")
            study       = m.get("study_instance_uid")
            own_series  = m.get("series_instance_uid")
            ref_series  = m.get("referenced_series_uid")
            ref_class   = m.get("referenced_sop_class") or ""

            def _best(triples):
                if ref_class:
                    return [(s, mod) for s, mod, sc in triples
                            if s != own_series and s != ref_series and sc == ref_class]
                return [(s, mod) for s, mod, _ in triples
                        if s != own_series and s != ref_series]

            same_study = _best(same_study_map.get((file_for, study), []))
            if same_study:
                m["candidate_series_uid"]   = same_study[0][0]
                m["candidate_modality"]     = same_study[0][1]
                m["candidate_confidence"]   = "same_study"
                m["all_candidates"]         = "; ".join(f"{s}({mod})" for s, mod in same_study)
                m["fix_direction"]          = "fix_referenced_series_for"
            else:
                activity = _best(activity_map.get(file_for, []))
                if activity:
                    m["candidate_series_uid"]   = activity[0][0]
                    m["candidate_modality"]     = activity[0][1]
                    m["candidate_confidence"]   = "same_activity"
                    m["all_candidates"]         = "; ".join(f"{s}({mod})" for s, mod in activity)
                    m["fix_direction"]          = "uncertain"
                else:
                    m["candidate_series_uid"]   = ""
                    m["candidate_modality"]     = ""
                    m["candidate_confidence"]   = "none"
                    m["all_candidates"]         = ""
                    m["fix_direction"]          = "fix_referencing_file_for"

        return for_mismatches

    def suggest_missing_ref_candidates(self, missing_refs):
        """Annotate missing SOP references with candidate series for relinking.

        Six-tier priority (first match wins per entry):
          1a. SOP found globally, series in current activity            → series_in_activity
          1b. SOP found globally, study in current activity             → referenced_study_in_activity
          1c. SOP found globally, neither series nor study here         → series_global
          2.  Same study as referencing file + matching FOR             → same_study_same_for
          3.  Matching FOR anywhere in activity                         → same_for
          4a. Same study + matching SOP class UID + count ≈ expected   → same_study_sop_class_count
          4b. Same study + matching modality  + count ≈ expected       → same_study_modality_count
          5.  Same patient in activity                                  → same_patient
          6.  No candidate                                              → none
        """
        def _set(entry, series, modality, confidence, note):
            entry["candidate_series_uid"] = series
            entry["candidate_modality"]   = modality
            entry["candidate_confidence"] = confidence
            entry["candidate_note"]       = note

        def _fmt(pairs):
            return "; ".join(f"{s}({m})" for s, m in pairs)

        sop_refs = [e for e in missing_refs
                    if e.get("category") == "sop" and e.get("missing")]
        if not sop_refs:
            return missing_refs

        all_sop_uids = [e["uid"] for e in sop_refs]

        # ── Tier 1: global SOP → series + study ────────────────────────────
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT fsc.sop_instance_uid, fs.series_instance_uid,
                            fs.modality, fst.study_instance_uid
            FROM file_sop_common fsc
            JOIN file_series  fs  ON fs.file_id  = fsc.file_id
            LEFT JOIN file_meta   fm  ON fm.file_id  = fsc.file_id
            LEFT JOIN file_study  fst ON fst.file_id = fsc.file_id
            WHERE fsc.sop_instance_uid = ANY(%s)
        """, (all_sop_uids,))
        sop_global = {}  # sop_uid → (series, modality, study)
        for sop, series, modality, study in cur.fetchall():
            sop_global[sop] = (series, modality or '', study)
        cur.close()

        cand_series  = list({v[0] for v in sop_global.values()})
        cand_studies = list({v[2] for v in sop_global.values() if v[2]})

        series_in_activity = set()
        if cand_series:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT fs.series_instance_uid
                FROM file_series fs
                JOIN activity_timepoint_file atf ON atf.file_id = fs.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fs.series_instance_uid = ANY(%s) AND at.activity_id = %s
            """, (cand_series, self.args.activity_id))
            series_in_activity = {row[0] for row in cur.fetchall()}
            cur.close()

        studies_in_activity = set()
        if cand_studies:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT fst.study_instance_uid
                FROM file_study fst
                JOIN activity_timepoint_file atf ON atf.file_id = fst.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fst.study_instance_uid = ANY(%s) AND at.activity_id = %s
            """, (cand_studies, self.args.activity_id))
            studies_in_activity = {row[0] for row in cur.fetchall()}
            cur.close()

        # ── Tiers 2–5: fallback data ─────────────────────────────────────
        needs_fallback = [e for e in sop_refs if e["uid"] not in sop_global]
        fb_for_uids    = list({e["file_for_uid"]       for e in needs_fallback if e.get("file_for_uid")})
        fb_study_uids  = list({e["study_instance_uid"] for e in needs_fallback if e.get("study_instance_uid")})
        fb_patient_ids = list({e["patient_id"]         for e in needs_fallback if e.get("patient_id")})

        # All fallback maps store (series, modality, sop_class) 3-tuples so SOP class
        # can be used as the primary filter in candidate selection.
        same_study_for_map = defaultdict(list)  # (for_uid, study_uid) → [(series, modality, sop_class)]
        same_for_map       = defaultdict(list)  # for_uid → [(series, modality, sop_class)]
        study_count_map    = defaultdict(list)  # study_uid → [(series, modality, sop_class, count)]
        patient_map        = defaultdict(list)  # patient_id → [(series, modality, sop_class)]

        if fb_for_uids and fb_study_uids:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT ff.for_uid, fst.study_instance_uid,
                                fs.series_instance_uid, fs.modality,
                                fsc.sop_class_uid
                FROM file_for ff
                JOIN file_series    fs   ON fs.file_id   = ff.file_id
                JOIN file_study     fst  ON fst.file_id  = ff.file_id
                LEFT JOIN file_sop_common fsc ON fsc.file_id = ff.file_id
                WHERE ff.for_uid = ANY(%s) AND fst.study_instance_uid = ANY(%s)
            """, (fb_for_uids, fb_study_uids))
            for for_uid, study_uid, series, modality, sop_class in cur.fetchall():
                same_study_for_map[(for_uid, study_uid)].append(
                    (series, modality or '', sop_class or ''))
            cur.close()

        if fb_for_uids:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT ff.for_uid, fs.series_instance_uid, fs.modality,
                                fsc.sop_class_uid
                FROM file_for ff
                JOIN file_series    fs  ON fs.file_id  = ff.file_id
                LEFT JOIN file_sop_common fsc ON fsc.file_id = ff.file_id
                JOIN activity_timepoint_file atf ON atf.file_id = ff.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE ff.for_uid = ANY(%s) AND at.activity_id = %s
            """, (fb_for_uids, self.args.activity_id))
            for for_uid, series, modality, sop_class in cur.fetchall():
                same_for_map[for_uid].append((series, modality or '', sop_class or ''))
            cur.close()

        if fb_study_uids:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT fst.study_instance_uid, fs.series_instance_uid,
                       fs.modality, fsc.sop_class_uid,
                       COUNT(DISTINCT fs.file_id) AS file_count
                FROM file_series  fs
                JOIN file_study   fst ON fst.file_id  = fs.file_id
                LEFT JOIN file_sop_common fsc ON fsc.file_id = fs.file_id
                JOIN activity_timepoint_file atf ON atf.file_id = fs.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fst.study_instance_uid = ANY(%s) AND at.activity_id = %s
                GROUP BY fst.study_instance_uid, fs.series_instance_uid,
                         fs.modality, fsc.sop_class_uid
            """, (fb_study_uids, self.args.activity_id))
            for study_uid, series, modality, sop_class, count in cur.fetchall():
                study_count_map[study_uid].append(
                    (series, modality or '', sop_class or '', count)
                )
            cur.close()

        if fb_patient_ids:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT DISTINCT fp.patient_id, fs.series_instance_uid, fs.modality,
                                fsc.sop_class_uid
                FROM file_patient fp
                JOIN file_series    fs  ON fs.file_id  = fp.file_id
                LEFT JOIN file_sop_common fsc ON fsc.file_id = fp.file_id
                JOIN activity_timepoint_file atf ON atf.file_id = fp.file_id
                JOIN activity_timepoint at ON at.activity_timepoint_id = atf.activity_timepoint_id
                WHERE fp.patient_id = ANY(%s) AND at.activity_id = %s
            """, (fb_patient_ids, self.args.activity_id))
            for patient_id, series, modality, sop_class in cur.fetchall():
                patient_map[patient_id].append((series, modality or '', sop_class or ''))
            cur.close()

        sop_count_per_file = defaultdict(set)
        for e in sop_refs:
            sop_count_per_file[e["file_id"]].add(e["uid"])

        # ── Annotate ─────────────────────────────────────────────────────────
        for entry in sop_refs:
            sop_uid    = entry["uid"]
            own_series = entry.get("series_instance_uid")
            file_for   = entry.get("file_for_uid")
            study      = entry.get("study_instance_uid")
            patient_id = entry.get("patient_id")
            file_id    = entry["file_id"]
            ref_class  = entry.get("referenced_sop_class") or ""

            def _best(triples):
                """SOP class match when ref_class is known; all candidates otherwise."""
                if ref_class:
                    return [(s, m) for s, m, sc in triples
                            if s != own_series and sc == ref_class]
                return [(s, m) for s, m, _ in triples if s != own_series]

            # Tier 1
            if sop_uid in sop_global:
                g_series, g_mod, g_study = sop_global[sop_uid]
                if g_series in series_in_activity:
                    _set(entry, g_series, g_mod, "series_in_activity",
                         "SOP found in this series; SOPs may have been regenerated")
                elif g_study and g_study in studies_in_activity:
                    study_cands = _best(study_count_map.get(g_study, []))
                    note = f"SOP series not here but study is; {_fmt(study_cands)}" if study_cands else \
                           "SOP found but its study has no series in this activity"
                    _set(entry, study_cands[0][0] if study_cands else g_series,
                         study_cands[0][1] if study_cands else g_mod,
                         "referenced_study_in_activity", note)
                else:
                    _set(entry, g_series, g_mod, "series_global",
                         "SOP found but neither its series nor study is in this activity")
                continue

            # Tier 2
            tier2 = _best(same_study_for_map.get((file_for, study), []))
            if tier2:
                _set(entry, tier2[0][0], tier2[0][1], "same_study_same_for", _fmt(tier2))
                continue

            # Tier 3
            tier3 = _best(same_for_map.get(file_for, []))
            if tier3:
                _set(entry, tier3[0][0], tier3[0][1], "same_for", _fmt(tier3))
                continue

            # Tier 4
            expected  = len(sop_count_per_file[file_id])
            tolerance = max(1, int(expected * 0.1))

            def _count_ok(s, cnt):
                return s != own_series and abs(cnt - expected) <= tolerance

            if study and expected:
                rows = study_count_map.get(study, [])

                # 4a: SOP class match
                if ref_class:
                    tier4a = [(s, m) for s, m, sc, cnt in rows
                              if sc == ref_class and _count_ok(s, cnt)]
                    if tier4a:
                        _set(entry, tier4a[0][0], tier4a[0][1], "same_study_sop_class_count",
                             f"SOP class {ref_class}, ~{expected} files; {_fmt(tier4a)}")
                        continue

                # 4b: modality match
                ref_mod = entry.get("modality") or ""
                tier4b  = [(s, m) for s, m, _, cnt in rows
                           if m == ref_mod and _count_ok(s, cnt)]
                if not tier4b:
                    tier4b = [(s, m) for s, m, _, cnt in rows if _count_ok(s, cnt)]
                if tier4b:
                    label = "same_study_modality_count" if ref_mod else "same_study_count"
                    _set(entry, tier4b[0][0], tier4b[0][1], label,
                         f"~{expected} files; {_fmt(tier4b)}")
                    continue

            # Tier 5
            tier5 = _best(patient_map.get(patient_id, []))
            if tier5:
                _set(entry, tier5[0][0], tier5[0][1], "same_patient", _fmt(tier5))
                continue

            _set(entry, "", "", "none", "")

        return missing_refs

    # ------------------------------------------------------------------
    # Report writers
    # ------------------------------------------------------------------

    def create_split_reference_reports(self, missing_refs):
        """Annotate notes, split into three buckets, and write one report each.

        Buckets:
          Missing_References  — not found anywhere in Posda
          External_References — found in Posda but outside the current activity/timepoint
          Found_References    — found within the current activity/timepoint
        """
        activity_id = str(self.args.activity_id)
        for entry in missing_refs:
            if entry.get("missing") is False:
                if str(entry.get("found_activity_id")) == activity_id:
                    entry["note"] = "In current activity"
                else:
                    entry.setdefault("note", "In external activity")

        missing_rows  = [reference_to_row(e) for e in missing_refs if e.get("missing")]
        external_rows = [reference_to_row(e) for e in missing_refs
                         if not e.get("missing")
                         and str(e.get("found_activity_id")) != activity_id]
        found_rows    = [reference_to_row(e) for e in missing_refs
                         if not e.get("missing")
                         and str(e.get("found_activity_id")) == activity_id]

        n_missing  = len(missing_rows)
        n_external = len(external_rows)
        n_found    = len(found_rows)

        print(f"Missing (Not in Posda): {n_missing}")
        print(f"External (Not in current Activity / Timepoint): {n_external}")
        print(f"Found (In current Activity / Timepoint): {n_found}")

        def _counts(entries):
            return {
                "patients": len({e.get("patient_id")           for e in entries} - {None}),
                "studies":  len({e.get("study_instance_uid")   for e in entries} - {None}),
                "for_uids": len({e.get("file_for_uid")         for e in entries} - {None}),
                "series":   len({e.get("series_instance_uid")  for e in entries} - {None}),
                "files":    len({e.get("file_id")              for e in entries} - {None}),
                "refs":     len(entries),
            }

        missing_entries  = [e for e in missing_refs if e.get("missing")]
        external_entries = [e for e in missing_refs
                            if not e.get("missing")
                            and str(e.get("found_activity_id")) != activity_id]
        found_entries    = [e for e in missing_refs
                            if not e.get("missing")
                            and str(e.get("found_activity_id")) == activity_id]

        cm, ce, cf = _counts(missing_entries), _counts(external_entries), _counts(found_entries)

        r = self.background.create_report("Reference_Summary")
        summary_writer = csv.writer(r, lineterminator='\n')
        summary_writer.writerow([
            "level",
            "Missing (Not in Posda)",
            "External (Not in current Activity / Timepoint)",
            "Found (In current Activity / Timepoint)",
        ])
        for level, label in (
            ("patients", "Patients"),
            ("studies",  "Studies"),
            ("for_uids", "Frame of Reference UIDs"),
            ("series",   "Series"),
            ("files",    "Files"),
            ("refs",     "References"),
        ):
            summary_writer.writerow([label, cm[level], ce[level], cf[level]])
        print("  -> Reference_Summary")

        for bucket, name in (
            (missing_rows,  "Missing_References"),
            (external_rows, "External_References"),
            (found_rows,    "Found_References"),
        ):
            if not bucket:
                continue
            for report_name in self.create_reference_reports(bucket, name):
                print(f"  -> {report_name}")

    def create_reference_reports(self, references, base_name, batch_size=250_000):
        """Write references in batches, returning the list of report names created."""
        if not references:
            return []
        batches = [
            references[i:i + batch_size]
            for i in range(0, len(references), batch_size)
        ]
        report_names = []
        for i, batch in enumerate(batches):
            name = f"{base_name}_{i}"
            r = self.background.create_report(name)
            writer = csv.writer(r, lineterminator='\n')
            writer.writerow(REFERENCE_REPORT_HEADER)
            for row in batch:
                writer.writerow(row)
            report_names.append(name)
        return report_names

    def create_for_mismatch_report(self, for_mismatches):
        """Create the FOR_Mismatches detail report."""
        if not for_mismatches:
            return
        r = self.background.create_report("FOR_Mismatches")
        writer = csv.writer(r, lineterminator='\n')
        writer.writerow(FOR_MISMATCH_HEADER)
        for entry in for_mismatches:
            writer.writerow([entry.get(k, "") for k in FOR_MISMATCH_HEADER])
        print("  -> FOR_Mismatches")

    def create_for_repair_reports(self, for_mismatches, description_a=None, description_b=None):
        """Generate two BackgroundEditTp CSVs to repair FOR mismatches in both directions."""
        if not for_mismatches:
            return
        description_a = description_a or "Repair FOR: align referencing files to referenced FOR"
        description_b = description_b or "Repair FOR: align referenced files to referencing FOR"
        header = ['series_instance_uid', 'op', 'tag', 'val1', 'val2',
                  'Operation', 'activity_id', 'edit_description', 'notify']

        def _write(name, items, series_key, for_key, description):
            r = self.background.create_report(name)
            writer = csv.writer(r, lineterminator='\n')
            writer.writerow(header)
            first, last_series = True, ''
            for entry in items:
                series = entry.get(series_key) or ''
                if not series:
                    continue
                if series != last_series:
                    if first:
                        writer.writerow([series, '', '', '', '', 'BackgroundEditTp',
                                         self.args.activity_id, description, self.args.notify])
                        first = False
                    else:
                        writer.writerow([series])
                    last_series = series
                writer.writerow(['', 'set_tag', '<(0020,0052)>', f'<{entry[for_key]}>', '<>'])
            print(f"  -> {name}")

        # Deduplicate by (referencing_series, referenced_series) before writing
        seen = set()
        deduped = []
        for e in for_mismatches:
            key = (e.get("series_instance_uid"), e.get("referenced_series_uid"))
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        _write(
            f"change_referencing_FORs_to_match_referenced_{self.args.background_id}",
            sorted(deduped, key=lambda e: e.get("series_instance_uid") or ""),
            "series_instance_uid", "referenced_for_uid", description_a,
        )
        _write(
            f"change_referenced_FORs_to_match_referencing_{self.args.background_id}",
            sorted(deduped, key=lambda e: e.get("referenced_series_uid") or ""),
            "referenced_series_uid", "file_for_uid", description_b,
        )

    def create_edit_skeleton(self):
        """Write a BackgroundEditTp skeleton CSV the user can fill in for batch edits."""
        r = self.background.create_report("Edit_Skeleton")
        writer = csv.writer(r, lineterminator='\n')
        writer.writerow(["series_instance_uid", "num_files", "op", "tag", "val1", "val2",
                         "Operation", "edit_description", "notify", "activity_id"])
        # BackgroundEditTp goes on the first series row only — not repeated for subsequent series.
        # Each tag that needs hashing requires its own op row beneath the series row.
        # Use [<0>] instead of [0] to match all sequence indices (pattern mode).
        writer.writerow(["<series_instance_uid>", None, None, None, None, None,
                         "BackgroundEditTp", "Edits from Linkage Check",
                         self.args.notify, self.args.activity_id])
        writer.writerow([None, None, "hash_unhashed_uid",
                         "<(XXXX,XXXX)[<0>](YYYY,YYYY)>", TCIA_UID_ROOT, "<>",
                         None, None, None, None])
        writer.writerow([None, None, "hash_unhashed_uid",
                         "<(XXXX,XXXX)[<0>](ZZZZ,ZZZZ)>", TCIA_UID_ROOT, "<>",
                         None, None, None, None])
        writer.writerow(["<series_instance_uid_2>", None, None, None, None, None,
                         None, None, None, None])
        writer.writerow([None, None, "hash_unhashed_uid",
                         "<(XXXX,XXXX)[<0>](YYYY,YYYY)>", TCIA_UID_ROOT, "<>",
                         None, None, None, None])
        writer.writerow([None, None, "hash_unhashed_uid",
                         "<(XXXX,XXXX)[<0>](ZZZZ,ZZZZ)>", TCIA_UID_ROOT, "<>",
                         None, None, None, None])
        print("  -> Edit_Skeleton")

    def create_relink_report(self, relink_items):
        """Generate a relink worklist for structural file rewrites (RT fix pipeline).

        relink_items: list of dicts with file_id and target_series_uid.
        The worklist is consumed by the fix script to rewrite DICOM files.
        """
        if not relink_items:
            return
        name = f"Relink_Worklist_{self.args.background_id}"
        r = self.background.create_report(name)
        writer = csv.writer(r, lineterminator='\n')
        writer.writerow(['file_id', 'target_series_instance_uid', 'candidate_confidence'])
        for item in relink_items:
            writer.writerow([item['file_id'], item['target_series_uid'],
                             item.get('candidate_confidence', '')])
        print(f"  -> {name}")
