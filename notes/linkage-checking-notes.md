# Linkage Checking — Working Notes

Team-shared planning notes for the linkage-checking feature set.

## Overview & current state

A Python replacement for a family of older Perl scripts that check whether DICOM objects
in a Posda activity correctly reference each other — missing references (a SEG/RTSTRUCT/
etc. pointing at a SOP/series/study/FOR UID that doesn't exist), and Frame-of-Reference
mismatches (a reference that resolves, but to a file whose FOR doesn't match). A shared
`LinkageChecker` base class (`linkage.py`) does the DB queries, DICOM-dataset walking, and
report writing; three thin per-modality scripts (`CheckLinkages.py`, `CheckSegLinkages.py`,
`CheckRtLinkages.py`) subclass it, plus one separate fixer (`FixLinkages.py`) that rewrites
files once a relink target is known. See "Files involved" and "Architecture" below.

**Active:** all three checkers — `linkage.py` (base), `CheckLinkages.py`
(general/all-modality), `CheckSegLinkages.py` (SEG), and `CheckRtLinkages.py` (RT) — are
wired into the UI via the "Run Consistency Checks" workflow step ("Check Consistency,"
"Check ALL Linkages," "Check SEG Linkages," "Check RT Linkages"). The old separate
"Segmentation Objects" workflow section and its "Examine Check Results" query
(`SegCheckQueries`) were retired — SEG's linkage check moved into "Run Consistency Checks"
alongside the others, and the query is no longer needed since the scripts return all the
needed reports directly. See "Workflow UI changes" below for the full list.

**Disabled by design in all three checkers:** the fix/relink suggestion logic
(`suggest_missing_ref_candidates()`/`suggest_relink_candidates()`), the RTSTRUCT relink
worklist that feeds `FixLinkages.py`, and the CSV columns that suggestion logic populates.
Only reference *checking* is active; suggested fixes and the Fix script are not. See
"Candidate suggestion and the Fix script are intentionally disabled" and "Report output —
candidate-suggestion columns" below for where this is implemented and how to re-enable it.

**Recent work:** a real performance fix (top-level sequence filtering now happens before
recursing into a DICOM dataset, not after), a single-pass rewrite of the reference-report
splitting logic (ref counts can run into the millions), an expanded
`REFERENCE_SEQUENCES_SEG` set (closes real SEG-to-volume linkage gaps — cross-study refs,
per-frame derivation refs), progress-message improvements, and bringing RT checking online
(wired into the UI, with candidate suggestion/relink worklist disabled to match the other
two checkers). Full detail in "Python code review — improvement ideas" below.

**Open / future work:** a legacy-Perl porting inventory (below) — most notably
`CheckStructLinkagesTpId.pl`'s internal ROI/contour consistency checks, not yet ported into
`RTLinkageChecker`, and concrete correctness gaps in `FixLinkages.py`'s RTSTRUCT relink
algorithm (no `StructureSetROISequence` FOR fixup, no geometry-based contour mapping, no
overlap validation). None of this blocks RT *checking* from being live, since the Fix
script and candidate suggestion stay disabled regardless. Full checklist in
"Ideas / TODO" at the bottom.

## Files involved

| File | Role |
|---|---|
| [posda/posdatools/python/posda/linkage.py](../posda/posdatools/python/posda/linkage.py) | `LinkageChecker` base class — all shared logic (DB queries, DICOM walking, candidate suggestion, report writers) |
| [posda/posdatools/Posda/bin/CheckLinkages.py](../posda/posdatools/Posda/bin/CheckLinkages.py) | `GeneralLinkageChecker` — all modalities, plus UID anomaly detection (dup SOPs, cross-category overlaps) |
| [posda/posdatools/Posda/bin/CheckSegLinkages.py](../posda/posdatools/Posda/bin/CheckSegLinkages.py) | `SegLinkageChecker` — SEG files only, scans `ReferencedSeriesSequence` + volume-overlay sequences (see below) |
| [posda/posdatools/Posda/bin/CheckRtLinkages.py](../posda/posdatools/Posda/bin/CheckRtLinkages.py) | `RTLinkageChecker` — RTSTRUCT/RTPLAN/RTDOSE/RTIMAGE, scans RT-specific ref sequences; candidate suggestion and the RTSTRUCT relink worklist are commented out for now |
| [posda/posdatools/Posda/bin/FixLinkages.py](../posda/posdatools/Posda/bin/FixLinkages.py) | Standalone fixer — reads a `Relink_Worklist` CSV, rewrites RTSTRUCT/SEG files to point at a corrected target series, writes to `$POSDA_CACHE_ROOT/edits/<uuid>/` for review before import. **Not wired up yet** — no checker currently produces a worklist for it to consume |

## Architecture

- `LinkageChecker` (linkage.py) is the shared base. Subclasses set `reference_sequences`
  to restrict which top-level DICOM sequences get walked:
  - `None` (CheckLinkages/general) → scan all nested UID tags
  - `REFERENCE_SEQUENCES_SEG` → volume-overlay reference sequences (see effectiveness section below)
  - `REFERENCE_SEQUENCES_RT` → FOR/structure-set/plan/dose reference sequences
- Common pipeline across all three checkers:
  1. `get_activity_files()` — pull latest activity_timepoint's DICOM files from DB
  2. `build_uid_context()` — build SOP/series/study/FOR UID sets + SOP→FOR / SOP→series maps
  3. `find_missing_references()` — walk each file's dataset, flag missing refs + FOR mismatches
  4. `annotate_missing_refs()` — look up "missing" refs globally across all of Posda (not just this activity)
  5. `suggest_missing_ref_candidates()` / `suggest_relink_candidates()` — tiered heuristics to propose a fix target
  6. `create_split_reference_reports()` / `create_for_mismatch_report()` / `create_for_repair_reports()` / `create_edit_skeleton()` — CSV report generation consumed by `BackgroundEditTp`

- Fix path is separate and currently disabled end-to-end: `CheckRtLinkages.py` has code
  (commented out) to build a `Relink_Worklist` CSV (RTSTRUCT only — FOR-only mismatches for
  RTPLAN/RTDOSE/RTIMAGE would be handled via tag-edit CSVs, not structural relink).
  `FixLinkages.py` is written to consume that worklist and do the actual DICOM rewrite
  (`fix_rtstruct` / `fix_seg`), diffing before/after with `ShortLongDicomCompare.pl` — but
  with no checker currently producing a worklist, it has nothing to run against.

## Candidate-suggestion tiers (for reference — not currently active, see Overview)

`suggest_missing_ref_candidates` (missing SOP refs), six tiers, first match wins:
1a/1b/1c. SOP found globally → series in activity / study in activity / neither
2. Same study + matching FOR
3. Matching FOR anywhere in activity
4a/4b. Same study + SOP class or modality + file count ≈ expected
5. Same patient in activity
6. No candidate

`suggest_relink_candidates` (FOR mismatches): same-study match (high confidence) →
same-activity fallback (low confidence) → none (fix_direction becomes "fix_referencing_file_for").

## Python code review — improvement ideas (2026-07-13)

Findings from reviewing linkage.py + the four bin/ scripts, before diving into the legacy
Perl port. Not yet actioned — see status per item.

### Performance — `walk_dataset_for_referencing` walks the whole dataset before filtering [DONE]

`reference_sequences` filtering happens *after* the full recursive walk
([linkage.py:277-279](../posda/posdatools/python/posda/linkage.py#L277-L279)):

```python
for _, elem, path, key_path in walk_dataset_for_referencing(ds):
    if self.reference_sequences is not None and key_path[0] not in self.reference_sequences:
        continue
```

`walk_dataset_for_referencing` calls `walk_dataset`, which unconditionally recurses into
*every* sequence/dataset item regardless of `reference_sequences` — so for SEG/RT files it
still walks into large irrelevant sequences (e.g. `SegmentSequence`, `ROIContourSequence`
contour-point data) just to discard every element found there. The discard check only
happens per-leaf-element, after the (potentially deep) recursion into that branch already
happened.

Impact scales with file complexity: SEG files with many segments, or RTSTRUCT files with
many ROIs/contours, pay the full traversal cost of branches that `reference_sequences`
was specifically introduced to skip (`REFERENCE_SEQUENCES_SEG` = just
`ReferencedSeriesSequence`; `REFERENCE_SEQUENCES_RT` = 6 specific sequences) — see
[linkage.py:26-37](../posda/posdatools/python/posda/linkage.py#L26-L37) for the sets.

**Fix (implemented 2026-07-13):** `walk_dataset` and `walk_dataset_for_referencing` now
take an optional `reference_sequences` param. At depth 0, an element whose keyword isn't
in that set is skipped before recursing in, instead of being filtered after the fact.
`reference_sequences=None` (used by `CheckLinkages.py`) is unchanged/unfiltered.
`find_missing_references` now passes `self.reference_sequences` straight into
`walk_dataset_for_referencing` and no longer re-filters by `key_path[0]` afterward.

Status: done — see [linkage.py:55-94](../posda/posdatools/python/posda/linkage.py#L55-L94).

### Candidate suggestion and the Fix script are intentionally disabled — by design, not a bug

All three checkers have `suggest_missing_ref_candidates()`/`suggest_relink_candidates()`
commented out:
[CheckLinkages.py:88-90](../posda/posdatools/Posda/bin/CheckLinkages.py#L88-L90),
[CheckSegLinkages.py:47-48](../posda/posdatools/Posda/bin/CheckSegLinkages.py#L47-L48),
[CheckRtLinkages.py:60-63](../posda/posdatools/Posda/bin/CheckRtLinkages.py#L60-L63). None
of them call `create_relink_report()` — `CheckRtLinkages.py`'s RTSTRUCT relink-worklist
block is present but commented out alongside its `suggest_relink_candidates()` call, since
the worklist depends on that call's output. `FixLinkages.py`'s `fix_rtstruct`/`fix_seg`
fixers exist but have no worklist producer feeding them; that's expected, not a gap to close.

Status: by design — do not uncomment/wire any of this up until candidate suggestion and
the Fix script are ready to ship.

### Architecture — duplicated `run()` pipeline across the three checkers

`CheckLinkages.py`, `CheckSegLinkages.py`, `CheckRtLinkages.py` each hand-roll the same
divider/print/scan/annotate/suggest/report sequence. Template-method candidate: base class
owns the pipeline shape, subclasses override "get source files" + a couple of hooks
(e.g. RT's relink-worklist step). Would shrink each script to just its modality-specific
bits and make it obvious when a step (like SEG's missing relink step, above) is skipped
vs. simply forgotten.

Status: idea only, no urgency — revisit after candidate suggestion/the Fix script ship and
the legacy port is settled.

### Maintainability — no test coverage for the candidate-suggestion tiers

`suggest_missing_ref_candidates`'s 6-tier logic and `suggest_relink_candidates`'s
same-study/same-activity fallback are the most intricate, most likely to silently regress
code in the file. Worth a handful of unit tests with synthetic UID sets before this becomes
the code everyone's afraid to touch.

Status: idea only.

### Report output — candidate-suggestion columns commented out for now [DONE, 2026-07-14]

`REFERENCE_REPORT_HEADER`'s `candidate_series_uid`/`candidate_modality`/`candidate_confidence`/
`candidate_note`, and `FOR_MISMATCH_HEADER`'s `candidate_series_uid`/`candidate_modality`/
`candidate_confidence`/`all_candidates`/`fix_direction`, were only ever populated by
`suggest_missing_ref_candidates()`/`suggest_relink_candidates()`. Since those calls are now
commented out in all three checkers (see "Candidate suggestion and the Fix script" above),
the columns are consistently absent from every report.

Commented out (not deleted) in three places, so it's a one-line uncomment to restore later:
`REFERENCE_REPORT_HEADER`, `FOR_MISMATCH_HEADER`, and `reference_to_row()`'s matching tuple
entries, in [linkage.py:42-56](../posda/posdatools/python/posda/linkage.py#L42-L56) and
[linkage.py:104-123](../posda/posdatools/python/posda/linkage.py#L104-L123).
`create_for_mismatch_report()` derives its row from `FOR_MISMATCH_HEADER` dynamically, so it
needed no separate edit.

Originally `CheckLinkages.py` *did* call `suggest_missing_ref_candidates()`/
`suggest_relink_candidates()` and would have populated these columns for real — asked
explicitly whether to restore them there while keeping SEG/RT blank; decided instead to
disable the `suggest_*` calls in `CheckLinkages.py` too (see above), so behavior is uniform
across all three rather than some checkers showing populated columns and others not.

Status: done.

### Performance — decided against parallelizing file loading

Investigated threading `find_missing_references`'s per-file `pydicom.dcmread` calls (I/O
release the GIL, so this looked like a cheap win). Checked how the rest of the repo does
concurrency first: `posda/posdatools/WorkerNode.py` confirms these background scripts
already run as one job among potentially many, concurrently, across a Redis-backed pool of
worker nodes — so a script-internal thread/process pool compounds load on top of that,
unpredictably. The only existing precedent in the repo
(`posda/posdatools/python/spreadsheet_from_dir.py`'s `multiprocessing.Pool()`) is
unbounded (defaults to all CPU cores) and is not a pattern to copy for a script that runs
inside an already-concurrent job queue.

Status: **rejected** — no script-internal parallelism added. If this becomes a real
bottleneck later, it needs a server-wide concurrency budget decision, not a per-script one.

### Effectiveness — expanded `REFERENCE_SEQUENCES_SEG` for volume-overlay linkage [DONE]

Priority for SEG specifically: the ability to link a SEG to the volume(s) it overlays.
Enumerated pydicom's data dictionary (tags verified against `DicomDictionary`, not
recalled from memory) for sequences that structurally carry this kind of link, then judged
relevance by how directly each maps to "which image/series does this SEG overlay":

- `ReferencedSeriesSequence` (0008,1115) — already scanned. The mandatory, series-level
  "this SEG overlays series X" declaration (Common Instance Reference Module).
- `SharedFunctionalGroupsSequence` (5200,9229) — **added.** Multi-frame Functional Groups;
  carries `DerivationImageSequence → SourceImageSequence` when one derivation applies to
  all frames (the common case). This is actually the *more* precise link than
  `ReferencedSeriesSequence` — the official Derivation Image Functional Group Macro,
  declaring which specific source image a frame overlays, not just which series. Cheap
  (typically one item).
- `StudiesContainingOtherReferencedInstancesSequence` (0008,1200) — **added.** Same
  category of info as `ReferencedSeriesSequence`, for the case where the overlaid volume
  lives in a different study than the SEG. Closes a real cross-study blind spot.
- `PerFrameFunctionalGroupsSequence` (5200,9230) — **added.** Same
  `DerivationImageSequence → SourceImageSequence` structure as the shared variant, but one
  item *per frame* — only populated when different frames derive from different source
  images. Real coverage gain, but on large multi-frame SEGs this reintroduces exactly the
  per-frame walking cost the [walk_dataset performance fix](#performance--walk_dataset_for_referencing-walks-the-whole-dataset-before-filtering-done)
  was protecting against. Added anyway per "prefer too many than too little," but worth
  watching if large-frame-count SEGs turn out to be slow to scan.
- `ReferencedImageEvidenceSequence` (0008,9092) — **added 2026-07-14.** Evidence/provenance
  image references; same rationale as the others, tag confirmed via `DicomDictionary`
  (not retired).

All nest UID keywords already in `UID_KEYWORDS` (`ReferencedSOPInstanceUID`,
`StudyInstanceUID`, `SeriesInstanceUID`), so no other code changes were needed —
`walk_dataset` recurses into them automatically once allowed at the top level. See
[linkage.py:26-32](../posda/posdatools/python/posda/linkage.py#L26-L32).

Status: done.

**RT got a similar addition (2026-07-14):** `ReferencedImageSequence` (0008,1140) added to
`REFERENCE_SEQUENCES_RT` — general-purpose source-image references, relevant to
RTIMAGE/RTDOSE. See [linkage.py:34-42](../posda/posdatools/python/posda/linkage.py#L34-L42).

### Workflow UI changes [DONE, 2026-07-14]

Changes to
[WorkflowDefinition.pm](../posda/posdatools/ActivityBasedCuration/include/ActivityBasedCuration/WorkflowDefinition.pm)
and `spreadsheet_operations/rows/`:

- Renamed the `6_concheck` workflow step from "Run Consistency Check" to
  "Run Consistency Checks."
- Renamed its "Check Linkages" button to "Check ALL Linkages" (`action => "CheckLinkages"`
  unchanged — only the caption changed).
- Removed the separate `11_linkrt` "Segmentation Objects" workflow section. Its one
  operation, now captioned "Check SEG Linkages" (was "Segmentation Linkages"), moved into
  `6_concheck` alongside "Check ALL Linkages."
- Appended "(Preview)" to all three linkage-checker captions — "Check ALL Linkages
  (Preview)," "Check SEG Linkages (Preview)," "Check RT Linkages (Preview)" — to flag that
  candidate suggestion and the Fix script aren't part of them yet (see "Candidate
  suggestion and the Fix script are intentionally disabled" above). "Check Consistency" is
  unrelated and unaffected.
- Removed `11_linkrt`'s "Examine Check Results" query (`SelectQueryGroup` /
  `query_list_name => "SegCheckQueries"`) — no longer needed, the script returns all
  needed reports directly. Also deleted the underlying `SegCheckQueries` entry from
  `%WorkflowQueries` (contained one query, `GetSegsAndLinkedFORsAfterCheck`). Confirmed
  zero remaining references to `SegCheckQueries` anywhere in the repo.
- Added a new "Check RT Linkages (Preview)" button (`action => "CheckRtLinkages"`) to `6_concheck`.
  Created [CheckRtLinkages.row](../posda/posdatools/spreadsheet_operations/rows/CheckRtLinkages.row)
  — this action had no `.row` descriptor at all before, so the button would have been
  non-functional without it. Mirrors the existing `CheckLinkages.row`/`CheckSegLinkages.row`
  pattern (`background_process`, `CheckRtLinkages.py <?bkgrnd_id?> <activity_id> <notify>`).

Net effect: "Run Consistency Checks" is now the single place all three linkage checkers are
triggered from.

## Legacy Perl scripts — porting inventory

Full-codebase scan (2026-07-13) for pre-Python linkage-checking / struct-relink logic. Goal:
make sure the Python `LinkageChecker` incorporates everything still relevant before we retire
the Perl scripts and their `.row` UI wiring.

### Still relevant — port or verify already covered

| Script | What it does | Notes |
|---|---|---|
| `Posda/include/Posda/StructFixer.pm` | Core relink module: FOR-check, geometry-check, nearest-Z contour-to-image relinking; rebuilds Referenced Study/FOR sequences + ROI FOR elements. Used by `TestStructFixerTp.pl`. | **Primary reference** for validating `FixLinkages.py`'s `fix_rtstruct` — compare algorithms directly. |
| `Posda/bin/SubProcessRelinkStruct.pl` | Alternate/more rigorous relink: computes per-image Z-slot ranges from actual IOP/IPP/pixel spacing (`Posda::FlipRotate`) instead of simple nearest-Z, explicitly errors on slice-spacing overlaps. | Worth comparing against `fix_rtstruct` — may be more correct than `StructFixer.pm`'s nearest-Z approach. |
| `Posda/bin/TestStructFixerTp.pl` (confirmed exists) | CLI: loads activity-scoped image geometry, calls `StructFixer::LinkStructSet()`, writes relinked file + report. | Direct precursor to `FixLinkages.py`'s repair path. |
| `Posda/bin/BackgroundFixStructLinkagesTp.pl` (confirmed exists) | Background daemon: reads worklist from STDIN, shells to `TestStructFixerTp.pl`, diffs via `ShortLongDicomCompare.pl`, records to `dicom_edit_compare_*` tables, emails Accept/Reject buttons. | The worklist+human-review+accept/reject pattern — check `FixLinkages.py` replicates this (it already does diff + email buttons; confirm DB disposition tracking parity). |
| `Posda/bin/CheckStructLinkagesTpId.pl` (confirmed exists) | **Not yet ported** — explicitly called out in `CheckRtLinkages.py` docstring. Internal ROI/contour cross-validation: `NumRois`, `SopsInVol`, `SopsLinkedToRoi`, `InternalLinkages`, `FrameOfRefExternal`, `VolumeFilesInPosda/Public`, `RoiFilesInPosda/Public`, `FrameOfReferenceMatches`, `UnlinkedClosedPlanar`. | **Highest-priority port target.** Distinct from the missing-ref/FOR-mismatch scan already in `CheckRtLinkages.py`. |
| `Posda/bin/PopulateFileRoiImageLinkagesByTimepoint.pl` | Populates `file_roi_image_linkages` table (ROI→contour→image SOP linkage rows + bounding box/type metadata) for an activity_timepoint. | Prerequisite data step for `CheckStructLinkagesTpId.pl`'s checks — needed if that logic is ported. |
| `Posda/bin/BackgroundDoseLinkageCheck.pl` | RTDOSE→RTPLAN reference check: exists, unique, matches collection/site/patient/SOP-class. | Likely mostly subsumed by `CheckRtLinkages.py`'s generic walk — verify collection/site/patient cross-checks aren't lost. |
| `Posda/bin/BackgroundPlanLinkageCheck.pl` | RTPLAN→RTSTRUCT reference check, same collection/site/patient-match pattern. | Same verification as above. |
| `Posda/bin/SubProcess/SubProcessStructLinkageReport.pl` | **Read in full (2026-07-13).** Subprocess worker (IPC via `fd_retrieve`/`store_fd`, not a standalone CLI): given an RTSTRUCT + pre-fetched image geometry (IPP/IOP/pixel spacing per SOP), verifies single IOP, builds a normalizing transform (`Posda::Transforms::NormalizingImageOrientation`), computes per-image Z-slots via `Posda::FlipRotate::ToCorners`, walks every CLOSED_PLANAR contour, computes min/avg/max Z, finds nearest image Z-slot. Called from `TciaCuration::SeriesReport.pm` (`WhenStructureSetAnalyzed`) — a different trigger path than the timepoint batch job, not timepoint-aware itself, no `.row` (internal helper only). | **Port this too** — genuinely new geometric contour-to-image logic, not duplicated by `CheckStructLinkagesTpId.pl`'s DB-only checks. Closest existing analog to the unimplemented `PointsWithinVolume` stub — worth mining directly for that. |
| `Posda/bin/BackgroundSingleRtLinkageDetailReports.pl` | **Read in full (2026-07-13).** Background job for a single RTSTRUCT file (`activity_id`, `file_path`, `notify`): shells out to `DumpLinkages.pl`, parses its pipe-delimited output into 3 CSV reports (VolumeReport, RoiReport, ContourReport), emails them. Confirmed live via `.row` (`BackgroundSingleRtLinkageDetailReports.row`, `background_process`) — this is the per-file drill-down UI report, complementary to `CheckStructLinkagesTpId.pl`'s bulk one-row-per-file summary. Not timepoint-aware itself; the wrapper is just CSV formatting/email plumbing. | **Skip this wrapper, but port `DumpLinkages.pl`** — the real per-file linkage/geometry logic lives there, not in this wrapper. **Reclassifies `DumpLinkages.pl`** — previously filed as a retirement-candidate debug tool; it's actually load-bearing for a live UI feature (see retirement list below, now corrected). |

### Retirement candidates (superseded, pre-timepoint, stub, or out-of-scope)

> **Correction (2026-07-13):** `DumpLinkages.pl` was originally listed here as a debug tool.
> It's actually the logic engine behind the live `BackgroundSingleRtLinkageDetailReports.pl`
> UI report (see table above) — moved to the porting inventory, **not** a retirement candidate.

Pre-timepoint duplicates of scripts above (superseded by the `Tp`/timepoint-aware versions):
- [ ] `Posda/bin/TestStructFixer.pl` (→ `TestStructFixerTp.pl`)
- [ ] `Posda/bin/BackgroundFixStructLinkages.pl` (→ `BackgroundFixStructLinkagesTp.pl`)
- [ ] `Posda/bin/CheckStructLinkages.pl` (→ `CheckStructLinkagesTpId.pl`)
- [ ] `Posda/bin/PopulateFileRoiImageLinkages.pl` (→ `PopulateFileRoiImageLinkagesByTimepoint.pl`)

Pre-DB / pre-`StructFixer.pm` duplicate algorithms, no DB or timepoint concept at all:
- [ ] `Posda/bin/FixRtStruct.pl`, `Posda/bin/FixRtStruct1.pl` — filesystem-only nearest-Z remap, near-duplicates of each other
- [ ] `Posda/bin/contrib/FixBadlyAnonymizedCtsAndStruct.pl` — one-off anonymization-migration variant of same algorithm
- [ ] `Posda/bin/CheckRtdoseLinkagesIntake.pl` — ad hoc intake-era script, reads raw DICOM tags directly instead of DB linkage tables

Stub / debug / tangential (not core linkage-checking logic):
- [ ] `Posda/bin/BackgroundStructLinkageCheck.pl` — unimplemented stub ("Checking Not currently implemented")
- [ ] `Posda/bin/SummarizeStructLinkagesByFileId.pl` — ad hoc debug/inspection tool
- [ ] `Posda/bin/SubProcess/SubProcessCloneStruct.pl` — file-management (clone/copy), not linkage logic
- [ ] `Posda/bin/FixForRtStructWithPixelOrFor.pl`, `posdatools/bin/FixMaastroStructs.pl` — DICOM-conformance cleanup, unrelated to reference linkage
- [ ] `Posda/bin/BulkHashStructUids.pl` — anonymization tool, touches the same UID elements but isn't linkage checking

`.row` UI descriptors to retire alongside their Perl scripts (confirmed legacy/non-Tp):
- [ ] `BackgroundFixRtstruct.row`
- [ ] `CheckStructLinkagesByCollectionSite.row`

(vs. currently-wired `BackgroundFixRtstructTp.row`, `CheckStructLinkagesTp.row`, both tagged `activity_timepoints` — keep these)

### Deep-dive: `CheckStructLinkagesTpId.pl` feature checklist (2026-07-13)

Full read-through of `Posda/bin/CheckStructLinkagesTpId.pl` to make sure nothing gets
silently dropped when this is ported into `RTLinkageChecker`.

**Control flow.** Args: `<bkgrnd_id> <activity_id> <check_public> <notify>`. Daemonizes,
then — critically — **shells out to `PopulateFileRoiImageLinkagesByTimepoint.pl $act_id`
first** and streams its output into the email report; the whole check assumes the
`file_roi_image_linkage` table is freshly repopulated before it runs. Scopes to the single
latest open activity_timepoint (`when_closed is null`, `ORDER BY activity_timepoint_id DESC
LIMIT 1`), gets all files in it, then filters to structure-set files via `GetSsByFileId`
(returns collection/site/patient/file_id — one row per RTSTRUCT). Report is CSV
(quoted fields, CRLF endings), one row per RTSTRUCT file, columns: `Collection, Site,
Patient, FileId, NumRois, SopsInVol, SopsLinkedToRoi, InternalLinkages,
FrameOfRefExternal, VolumeFilesInPosda, VolumeFilesInPublic, RoiFilesInPosda,
RoiFilesInPublic, FrameOfReferenceMatches, UnlinkedClosedPlanar, PointsWithinVolume,
Warnings`.

**Per-check breakdown** (checks run in this order — later checks read hash state set by
earlier ones, see "ordering dependency" below):

| Check | What it computes | What a flagged row means |
|---|---|---|
| `NumRois` | Per-ROI geometric-type counts (`ContourTypesByRoi`) | An ROI mixing >1 geometric type (e.g. CLOSED_PLANAR + POINT) in one ROI is suspicious — flagged as a warning |
| `SopsInVol` | Distinct (SOP, class, study, series, FOR) referenced in the struct's own Ref-FOR/Contour-Image sequences | Duplicate SOP in volume; FOR UID colliding with a SOP/Study/Series UID; >1 distinct FOR/series/study/SOP-class referenced by one struct (should normally be exactly one) |
| `SopsLinkedToRoi` | Distinct SOPs per contour geometric type, from the `file_roi_image_linkage` table | Informational count, not pass/fail |
| `InternalLinkages` | Cross-checks ROI↔SOP linkage table against `SopsInVol` + `Rois` | Linked SOP with >1 SOP class; linked SOP not present in the struct's own volume sequence (orphaned reference); SOP class mismatch; ROI's declared FOR ≠ FOR of any SOP its contours reference |
| `FrameOfRefExternal` | Groups struct's referenced SOPs by series→FOR, then queries the *actual* FOR of image files in Posda for that series | Struct's declared FOR doesn't match any FOR actually present on the real image files — catches stale/wrong FOR references |
| `VolumeFilesInPosda` / `VolumeFilesInPublic` | Existence check: do the struct's referenced volume SOPs actually exist as ingested files (Posda schema / Public schema)? | `"Found: N; Not found: M"` — Public variant only runs if `check_public` flag set |
| `RoiFilesInPosda` / `RoiFilesInPublic` | Same existence check, but scoped per contour geometric type over ROI-linked SOPs | Found/not-found broken out by geometric type |
| `FrameOfReferenceMatches` | Compares each ROI's declared FOR to the FOR actually found on its linked contour-image SOP (**depends on `VolumeFilesInPosda` having already run** — reuses its lookup) | Per-type mismatch counts |
| `UnlinkedClosedPlanar` | CLOSED_PLANAR contours with no row in `contour_image` (not linked to any referenced image) — the only check hard-coded to one geometric type | Lists affected ROI names |
| `PointsWithinVolume` | **Stub — "Not Currently Implemented".** Not a real check. | Must not be silently implemented as if it were real |
| `Warnings` | Aggregates the warning list from `NumRois`/`SopsInVol`/`InternalLinkages`/`FrameOfRefExternal` into one free-text column | Catch-all secondary channel, separate from the pass/fail columns |

**Ordering dependency to preserve (or make explicit) in the port:** `FrameOfReferenceMatches`
reuses data populated by `VolumeFilesInPosda`; `InternalLinkages`/`SopsLinkedToRoi` reuse data
populated by `SopsInVol`. The Perl version does this via implicit shared-hash mutation across
sequential subroutine calls — the Python port should make these dependencies explicit
(e.g. pass structured results between methods) rather than replicate the implicit ordering.

**Dead code / do-not-port-as-is:** unused `Digest::MD5` import; `%SeriesInOldTp` built via
`SeriesForFile` but never read; `PointsWithinVolume` is a full stub; `"???"` is an ad hoc
fallback sentinel string in `RoiFilesInPosda`/`RoiFilesInPublic` when there's nothing to
report — should become an explicit null/enum in Python, not a replicated magic string. Also
note the script's own in-code comment: `"##### This is a test version of this script #####"`
— worth confirming with stakeholders whether this logic is considered authoritative before
treating it as a spec.

### Deep-dive: relink algorithm comparison — StructFixer.pm vs SubProcessRelinkStruct.pl vs fix_rtstruct (2026-07-13)

Three different contour-to-image relinking algorithms exist. Summary first, then gap list.

| Capability | `StructFixer.pm` | `SubProcessRelinkStruct.pl` | `fix_rtstruct` (Python, current) |
|---|---|---|---|
| Contour→image mapping basis | Nearest raw Z (single first-point Z from ContourData) | Z-slot containment using true 3D corner geometry (IOP/IPP/pixel spacing via `Posda::FlipRotate::ToCorners`) + average-of-all-points Z | **Sorted lexicographic UID pairing — no geometry/Z used at all** |
| Self-identity shortcut (SOP already in target series → keep as-is) | No | No | Yes (Python-only addition) |
| Oblique/rotated-slice support | No — requires axial IOP, soft-errors otherwise | **Yes** — real corner projection | No — not applicable, no geometry used |
| Overlap / slice-spacing validation | None | **Yes — hard abort if adjacent Z slots overlap** | **None** |
| Unmapped contour handling | Always finds *some* nearest match (no failure mode) | Hard abort if Z falls in no slot | Reports "Unmapped contour SOP" but still writes the file (partial success) |
| Referenced Study/Series/FOR sequence rebuild | Full rebuild, groups by study→series→sorted-Z images, handles multiple studies/series | Full delete-and-rebuild, single study/series, hardcoded placeholder RT-Study SOP-class UID | Patches existing items in place, single series only |
| `StructureSetROISequence` FOR fixup `(3006,0020)[i](3006,0024)` | Yes — blanket: sets FOR on every ROI item | Yes — precise: resolves via Referenced ROI Number to exactly one matching ROI, aborts if ambiguous | **Not implemented at all — ROIs keep stale FOR after relink** |
| Error philosophy | Soft-accumulate, caller must inspect `$this->{errors}` | Hard abort via subprocess `Error()`, partial output never written | Returns `(success, errors)`, caller marks row Failed/OK but still writes file even with partial errors |

**Concrete gaps in `fix_rtstruct` vs. the Perl versions, ranked:**
1. **No `StructureSetROISequence` FOR fixup at all** — clearest, lowest-risk gap to close first (both Perl versions do this; Python never touches `(3006,0020)[i](3006,0024)`).
2. **No geometry-based contour mapping** — current lexicographic-UID pairing has no spatial basis and will silently mis-link whenever SOP UID sort order doesn't match spatial (Z) order. This is the most consequential gap.
3. **No overlap/slice-spacing validation** — `SubProcessRelinkStruct.pl` hard-fails on overlapping Z slots; Python has no equivalent safety check.
4. Multi-study/multi-series Referenced-Study-Sequence rebuild (StructFixer's capability) isn't replicated, though this is a less common case than #1-#3.

**Recommendation if pursuing parity:** adopt `SubProcessRelinkStruct.pl`'s approach over
`StructFixer.pm`'s — it's strictly more rigorous (real corner geometry vs. axial-only nearest-Z,
explicit overlap detection, precise ROI-Number-based FOR resolution vs. blanket). Start with
the ROI FOR fixup (cheap, clear-cut), then geometry-based mapping, then overlap validation.

### Open questions / things to dig into next

- [x] Read `SubProcessStructLinkageReport.pl` and `BackgroundSingleRtLinkageDetailReports.pl` in full — determine if they duplicate `CheckStructLinkagesTpId.pl` or add something new. **Done 2026-07-13** — both are complementary, not duplicates; see porting-inventory table above. `DumpLinkages.pl` was reclassified as a result.
- [ ] Does `BackgroundFixStructLinkagesTp.pl`'s `dicom_edit_compare_disposition`/`dicom_edit_compare_fixed` DB tracking have an equivalent in the new Python accept/reject flow, or does that state live only in email buttons today?
- [ ] Confirm with stakeholders whether `CheckStructLinkagesTpId.pl` (marked "test version" in its own source) is actually the authoritative spec before treating its checklist as gospel.
- [ ] Decide: blanket ROI-FOR fixup (StructFixer style, simpler) vs. ROI-Number-precise fixup (SubProcessRelinkStruct style, safer for multi-FOR ROI sets) when implementing the FOR fixup in `fix_rtstruct`.

## Ideas / TODO

- [ ] **Close the `StructureSetROISequence` FOR-fixup gap in `fix_rtstruct`** (FixLinkages.py) — clearest, lowest-risk win identified in the relink comparison above.
- [ ] Add geometry-based (Z-slot) contour-to-image mapping to `fix_rtstruct`, replacing the lexicographic-UID fallback — the most consequential correctness gap found.
- [ ] Add overlap/slice-spacing validation to `fix_rtstruct`, mirroring `SubProcessRelinkStruct.pl`'s hard-abort-on-overlap check.
- [ ] Port `CheckStructLinkagesTpId.pl`'s internal-consistency checks into `RTLinkageChecker`, preserving the NumRois → SopsInVol → InternalLinkages/FrameOfRefExternal → VolumeFilesInPosda → FrameOfReferenceMatches data-flow ordering (see deep-dive above); explicitly drop `PointsWithinVolume` (unimplemented stub) rather than porting it as a real check.
- [ ] Port `SubProcessStructLinkageReport.pl`'s geometric contour-to-image Z-matching logic — candidate implementation for the still-unimplemented `PointsWithinVolume` check.
- [ ] Port `DumpLinkages.pl`'s per-file linkage/geometry logic (backs the live `BackgroundSingleRtLinkageDetailReports.pl` UI report — reclassified from retirement candidate, see above).
- [ ] Verify RTDOSE/RTPLAN collection-site-patient cross-checks aren't lost vs. `BackgroundDoseLinkageCheck.pl` / `BackgroundPlanLinkageCheck.pl`
- [ ] Plan retirement of the non-Tp Perl scripts + their `.row` files once parity is confirmed
- [ ] **Re-enable candidate suggestion and the Fix script**, when ready: uncomment `suggest_missing_ref_candidates()`/`suggest_relink_candidates()` in all three checkers (`CheckLinkages.py`, `CheckSegLinkages.py`, `CheckRtLinkages.py`), the RTSTRUCT relink-worklist block in `CheckRtLinkages.py`, and the candidate-suggestion columns in `REFERENCE_REPORT_HEADER`/`FOR_MISMATCH_HEADER`/`reference_to_row()` (linkage.py) — all commented out (not deleted) for easy restoration, see "Candidate suggestion and the Fix script" and "Report output" notes above.
