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
`CheckStructLinkagesTpId.pl`'s internal ROI/contour consistency checks, now planned as a
separate general-purpose RTSTRUCT ROI checker rather than an extension of
`RTLinkageChecker` (see "RTSTRUCT ROI checker — plan"), and concrete correctness gaps in
`FixLinkages.py`'s RTSTRUCT relink algorithm (no `StructureSetROISequence` FOR fixup, no
geometry-based contour mapping, no overlap validation). None of this blocks RT *checking*
from being live, since the Fix script and candidate suggestion stay disabled regardless.
Full checklist in "Ideas / TODO" at the bottom.

**StructFixer.pm fixes:** two bugs in the legacy Perl relinker were fixed — an exact-equality
axial test that rejected near-axial images, and an ROI frame-of-reference loop that created
empty `StructureSetROISequence` items. See "StructFixer.pm bugs fixed".

## Files involved

| File | Role |
|---|---|
| [posda/posdatools/python/posda/linkage.py](../posda/posdatools/python/posda/linkage.py) | `LinkageChecker` base class — all shared logic (DB queries, DICOM walking, candidate suggestion, report writers) |
| [posda/posdatools/Posda/bin/CheckLinkages.py](../posda/posdatools/Posda/bin/CheckLinkages.py) | `GeneralLinkageChecker` — all modalities, plus UID anomaly detection (dup SOPs, cross-category overlaps) |
| [posda/posdatools/Posda/bin/CheckSegLinkages.py](../posda/posdatools/Posda/bin/CheckSegLinkages.py) | `SegLinkageChecker` — SEG files only, scans `ReferencedSeriesSequence` + volume-overlay sequences (see below) |
| [posda/posdatools/Posda/bin/CheckRtLinkages.py](../posda/posdatools/Posda/bin/CheckRtLinkages.py) | `RTLinkageChecker` — RTSTRUCT/RTPLAN/RTDOSE/RTIMAGE, scans RT-specific ref sequences; candidate suggestion and the RTSTRUCT relink worklist are commented out for now |
| [posda/posdatools/python/posda/rtstruct.py](../posda/posdatools/python/posda/rtstruct.py) | RTSTRUCT ROI checker library — model of one structure set, rules, edit planning and `BackgroundEditTp` sheet writer (see "RTSTRUCT ROI checker — plan") |
| [posda/posdatools/Posda/bin/CheckRtStructRois.py](../posda/posdatools/Posda/bin/CheckRtStructRois.py) | `RtStructRoiChecker` — runs the `rtstruct` rules over every RTSTRUCT in the latest timepoint; writes `RTSTRUCT_ROI_Findings`, `RTSTRUCT_ROI_Inventory` (one row per ROI per file, with a status) and, when anything is safely deletable, `RTSTRUCT_ROI_Edits`. Each is split into `_0`, `_1`, ... of at most 750,000 rows via `LinkageChecker.create_batched_reports` (the linkage reports use the same helper at 250,000); edit sheets split only on group boundaries. Button "Check RT Structure Set ROIs" in the RT linkage workflow step, after "Link RT Data" ([CheckRtStructRois.row](../posda/posdatools/spreadsheet_operations/rows/CheckRtStructRois.row)) |
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
| `StructureSetROISequence` FOR fixup `(3006,0020)[i](3006,0024)` | Yes — blanket: sets FOR on every ROI item (**was buggy** — indexed by ROI Contour item position, creating empty ROI items; fixed, see "StructFixer.pm bugs fixed") | Yes — precise: resolves via Referenced ROI Number to exactly one matching ROI, aborts if ambiguous | **Not implemented at all — ROIs keep stale FOR after relink** |
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
- [ ] ROI checker: should *unique* orphan ROI Contour items (contours found in no declared ROI) ever be included in generated edits, e.g. behind a flag, or always report-only?
- [ ] ROI checker: handle multi-file RTSTRUCT series via `BackgroundEditBySopInstanceTp`, or just skip and flag them?
- [ ] ROI checker: RTPLAN Dose Reference Sequence and RTDOSE DVH Referenced ROI Sequence also carry Referenced ROI Numbers (`3006,0084`) pointing into a referenced structure set — in scope, and in which phase?
- [ ] ROI checker: surface the existing ingest-time `dicom_process_errors` rows for undeclared ROI references, or rely solely on reading the files?
- [x] ROI checker: script name, workflow placement, caption. **Decided:** `CheckRtStructRois.py`, button "Check RT Structure Set ROIs" after "Link RT Data", no "(Preview)".
- [ ] Decide: blanket ROI-FOR fixup (StructFixer style, simpler) vs. ROI-Number-precise fixup (SubProcessRelinkStruct style, safer for multi-FOR ROI sets) when implementing the FOR fixup in `fix_rtstruct`. Either way, iterate the `StructureSetROISequence` itself — StructFixer's blanket version was indexing by ROI Contour item position (see "StructFixer.pm bugs fixed").

## StructFixer.pm bugs fixed

Two bugs in [StructFixer.pm](../posda/posdatools/Posda/include/Posda/StructFixer.pm), the relinker
behind `TestStructFixerTp.pl` / `BackgroundFixStructLinkagesTp.pl`.

### Axial test used exact float equality [FIXED]

`CheckImagGeo` compared ImageOrientationPatient against `1,0,0,0,1,0` with `==`. The
`sprintf("%.8f")` applied first keeps 8 decimals, so it absorbed nothing — a direction cosine
off by rounding noise on the order of 1e-5 (~0.001°) failed the test.

Why that was silent: rejection is soft — the image goes into `{errors}` but is never added
to `ImgsByZ`, the only table `LinkStructSet` maps contours against. With every image
rejected, `BuildCtMap` searches an empty table and returns undef, `abs($closest_z - $z)`
degenerates to `|z|` (so the reported `min_dist`/`max_dist` are contour Z coordinates, not
match distances), every contour's `ReferencedSOPInstanceUID` is looked up through an undef
key, and `LinkStructSet` still returns 1. `TestStructFixerTp.pl` prints `Linked:` and
`BackgroundFixStructLinkagesTp.pl` reports `status = OK` — the `errors` column is
informational only and never affects status.

**Fix:** compare each component against `$IopAxialTolerance = 1e-4` (~0.006°). Acceptance is
a strict superset of before (the old `sprintf` slack was ≤5e-9); checked old vs new
predicate over exact, 8dp, tilted, `-0.00000000`, sagittal, coronal, 1°/15° oblique and
malformed 3/5/7-element IOP values — 0 regressions. The `sprintf` moved into the error
message, which prints identical text.

**Deliberately not changed (backward compatibility):** the fail-open path itself. A genuinely
oblique, sagittal or coronal series still rejects every image and still produces undefined
references reported as OK. Candidate follow-up guards, all in `StructFixer.pm`:
- `LinkStructSet` returns 0 when `ImgsByZ` is empty — `TestStructFixerTp.pl` then prints
  `Not linked`, the background script sets `status = Failed` and skips writing the file;
  no change needed outside the module.
- Return 0 on an undefined `$closest_z`; have `BuildCtMap` record an error instead of
  storing undef.
- Optional max link distance (e.g. half the median slice spacing). Unlike the others this
  can fail files that previously "succeeded" (contours legitimately between slices).

### ROI frame-of-reference loop indexed the wrong sequence [FIXED]

The "Fix frames of reference in Structure Set ROI sequence" block built `$for_ref` from
`(3006,0020)` but then looped over `$ct_cont_ref` — one entry per CLOSED_PLANAR contour,
from `(3006,0039)`. `Substitutions` always puts `<0>` at tuple position 0, so
`$inst->[$for_ref->{index_list}->{"<0>"}]` yielded the **ROI Contour Sequence** index, which
was then used as a **Structure Set ROI Sequence** index.

- Harmless when the two sequences are 1:1 in the same order — which is why it went unnoticed.
- When a file has more ROI Contour items than declared ROIs, `InsertElementBySig` on a
  nonexistent index creates a blank item (`new_blank`, [Dataset.pm](../posda/posdatools/Posda/include/Posda/Dataset.pm)
  `InsertElementBySig`) holding only `(3006,0024)` — empty ROI items with no ROI Number,
  Name or Generation Algorithm, which dciodvfy flags. When orders differ it also writes the
  FOR to the wrong ROI.
- `$num_fors` counted only ROIs that already had `(3006,0024)`, so the
  `Replaced N of M roi frames of reference` report line was meaningless.
- The empty items are unreferenceable (every ROI reference resolves by ROI Number), so
  deleting them is safe. They are also invisible to ingest (both `Modules.pm` and
  `rt_structure.py` iterate on `(3006,0020)[<0>](3006,0022)`), so no DB-based check sees them.

**Fix:** loop over `$for_ref` itself, built on `(3006,0022)` ROI Number (Type 1 — every real
ROI has one) instead of `(3006,0024)` (which would only enumerate ROIs that already carry a
FOR). Verified with the real `Posda::Try` / `Posda::Dataset` / `LinkStructSet` on an RTSTRUCT
with more ROI Contour items than ROIs: old code added one empty item per excess contour
item; new code left the ROI sequence unchanged.

**Behavior change:** every declared ROI now gets the image FOR, including ROIs with no
CLOSED_PLANAR contours (the old loop only reached the indices of items that had them, at the
wrong position). Consistent with StructFixer's single-FOR model — it already forces the
top-level Referenced FOR to the image FOR.

### Pre-existing behavior noted, not changed

- The RT Referenced Study Sequence rebuild writes `$this->{ImgSopClass}` (the *image* SOP
  class) into `(3006,0010)[0](3006,0012)[n](0008,1150)`, a study-level Referenced SOP Class
  UID. The conventional value there is the retired Detached Study Management SOP class
  (`1.2.840.10008.3.1.2.3.1`). Every relinked file gets this element changed.
- The contour loop relinks every CLOSED_PLANAR contour unconditionally, overwriting existing
  links. Useful as a regression check: on a struct whose links are already correct, a correct
  relink reproduces them exactly, so the edit diff shows no change under `(3006,0039)`.
- `ShortLongDicomCompare.pl` replaces UIDs with `<uid>` / `<changed uid>`, so its diffs show
  *which* tags changed but never the values written.

### Testing StructFixer without the full Posda stack

`Posda::Config` is the only module in the `Posda::Try` → `Posda::Dataset` chain that needs
`Modern::Perl`, and `Dataset` only calls `Config()` when writing. Stubbing it lets the real
parser and `StructFixer` run under a bare Perl:

```perl
BEGIN {
  $INC{'Posda/Config.pm'} = 'stub';
  package Posda::Config;
  sub Config { return '' }
  sub import { no strict 'refs'; *{caller() . '::Config'} = \&Config }
}
```

Then `perl -I posda/posdatools/Posda/include ...`, build a fake `ImgsByUid` (iop/ipp/for_uid/
sop_class_uid/file), call `Posda::StructFixer->new(\%Info)->LinkStructSet($try->{dataset})`.
Pure-geometry code (`CheckImagGeo`) can be tested with `Posda::Try`/`Posda::Dataset` faked
entirely via `%INC` plus a no-op `Posda::Dataset::InitDD`.

## RTSTRUCT ROI checker — plan (2026-10-12)

A general-purpose Python checker for the internal consistency of RTSTRUCT files, designed so
the internal checks of the Perl RT check/fix scripts can be absorbed into it over time.
Separate from `CheckRtLinkages.py`, which checks references *between* files; this checks
consistency *within* one RTSTRUCT.

### Existing coverage

| Check | Where today | Gap |
|---|---|---|
| ROI Contour item / RT ROI Observation referencing an undeclared ROI Number | Ingest — `Modules.pm` (`RoiContour`, `RtRoiObservations`) and [rt_structure.py](../posda/posdatools/python/posda/ingest/rt_structure.py) | Recorded as `dicom_process_errors` rows (non-fatal; the item is skipped, the rest of the file ingests). Not surfaced by any check report; no fix path. |
| Structure Set ROI item with no ROI Number | Nowhere — ingest iterates on `(3006,0022)` and silently skips it | Only dciodvfy catches it, as missing attributes |
| Missing Type 1/2 attributes | `BackgroundDciodvfyTp.pl` | Generic conformance; no cross-sequence references |
| ROI counts, mixed geometric types, unlinked contours, FOR matches, volume files exist | `CheckStructLinkagesTpId.pl` | Reads the DB, so blind to anything ingest dropped |
| Per-file volume / contour / ROI tables | `DumpLinkages.pl` (behind `BackgroundSingleRtLinkageDetailReports.pl`) | Dump only, no checks |
| References between files, FOR mismatch | `CheckRtLinkages.py` | Doesn't look inside the RTSTRUCT's own sequences |
| Contour-to-slice geometry | `SubProcessStructLinkageReport.pl` | Different trigger path, not activity-wide |

### Design principle: read the DICOM, not the DB projection

The DB tables are a lossy projection of an RTSTRUCT: ingest drops exactly the malformed items
(orphan contour items and observations skipped, ROI items without an ROI Number silently
ignored). Any checker built on `roi` / `roi_contour` / `file_roi_image_linkage` reports such
files as clean. The checker reads RTSTRUCT structure from the file and uses the DB only for
cross-file context (which images exist in the activity, their FORs and geometry).

Related ingest quirk: `SimplerDicomAnalysis.pm` builds its ROI list from declared ROI Numbers
but also auto-creates ROI entries from `RTROIObservationsSequence` ROI Numbers. An undeclared
ROI that still has an observation entry therefore gets its contours collected, and
`PopulateFileRoiImageLinkagesByTimepoint.pl` finds no `roi_id` for it — inserts into
`file_roi_image_linkage` (`roi_id NOT NULL`) are expected to fail once those contours carry
image links. How `RunQuery` surfaces that failure is unconfirmed.

### Never treat an unreadable file as clean

`load_dataset` reads with `dcmread(force=True)`. An HTML page, a JSON error or an empty body
(e.g. a moved or misconfigured API URL answering 200) parses into a near-empty dataset with
no error. That dataset has no ROI items, so every rule passes and the file looks clean.

`rtstruct.dataset_problem()` checks that the SOP Class UID is RT Structure Set Storage and
that the SOP Instance UID matches the DB row. A file that fails is reported as
`file_not_checked` instead of being checked, and the run finishes with
`Complete; N file(s) could not be checked`. For the first such file under `POSDA_API_ONLY`,
`CheckRtStructRois.py` prints the API response (URL, status, content type, first bytes).

`LinkageChecker.load_dataset` itself has no such guard, so the linkage checkers have the same
gap: a non-DICOM response there produces no references and no findings (see TODO).

### Report upload pitfalls (`BackgroundProcess`)

- `_close_reports()` uploads reports in order with no error handling. If one `insert_file`
  fails, the loop stops: later reports are never closed or uploaded, and their temp files can
  be left at 0 bytes.
- `requests` drops the body when it follows a 301 on a PUT. An `http://` API URL that
  redirects to `https://` therefore uploads an empty body, and the API rejects it with a 422
  digest mismatch. Configure the API URL as `https://` directly.

### Shape

- **Library first, thin scripts on top** — what makes it absorbable later.
- **Model of one RTSTRUCT** (e.g. `posda/rtstruct.py`): declared ROIs (`3006,0020`), ROI
  Contour items with Referenced ROI Number and contours (type, points, z, image refs), RT ROI
  Observations (and related-ROI refs), referenced volume (`3006,0010`). `DumpLinkages.pl`'s
  three tables are this model printed.
- **Rules** are small functions over the model yielding findings: severity, location,
  fixable or not, and an optional proposed edit.
- **Outputs:** findings report; a filled-in `BackgroundEditTp` spreadsheet (same layout as
  `create_edit_skeleton` in [linkage.py](../posda/posdatools/python/posda/linkage.py)) for fixes
  that are safe deletions or value sets. Structural rewrites (relinking) stay with a relinker.
- **Leave generic conformance to dciodvfy.** Rules cover what it can't see: references
  across sequences, linkage, geometry.
- Reuse `LinkageChecker` plumbing (activity file query, `load_dataset` incl. `POSDA_API_ONLY`,
  background reports) rather than duplicating it.

### Edit pipeline constraints (for generated edits)

- `delete_tag` on a tag ending in `[n]` runs in "item" mode and deletes the whole sequence
  item ([ProcessBackgroundEditInstructions.pm](../posda/posdatools/Posda/include/Posda/ProcessBackgroundEditInstructions.pm) `ProcessIndividualEdit`).
- Item deletion uses `splice` (`Dataset.pm` `DeleteElementBySig`), so later items renumber.
  Edits are accumulated in input order and applied in that order with no sorting
  (`NewSubprocessEditor.pl` `@effective_edits`). **Emit deletes per sequence from the highest
  index down**, or the wrong items get deleted.
- `BackgroundEditTp` targets a `series_instance_uid`; every file in the series gets the same
  edits. Index-based item deletes are only safe for single-file series — skip and flag
  multi-file series (or evaluate `BackgroundEditBySopInstanceTp`, input
  `<unmapped_uid><mapped_uid><sop_instance_uid><operation><tag><val1><val2>`).
- `delete_tag` on a tag that ends in an *element* inside an item, e.g.
  `(3006,0020)[n](3006,0024)`, deletes only that element. The item stays, and if that was its
  last element Posda writes it out as an empty item — still invalid, and invisible in diffs.
  Removing an item requires the tag to end in `[n]`.
- Deleting every item of a sequence leaves the sequence present with zero items. That is
  non-conformant for these Type 3 "One or more Items" sequences (dciodvfy: "Bad Sequence
  number of Items = <0>"), and invisible in edit diffs. Delete the sequence itself instead:
  `delete_tag` on the bare tag, e.g. `<(3006,0080)>`, runs in "exact" mode and removes the
  whole element (`NewSubprocessEditor.pl` → `$ds->Delete`).
- Index lists must come from the file itself. A list built from counts outside the file (e.g.
  an assumed number of real ROIs) deletes a real ROI as soon as one count is wrong.

### Reading edit diffs (`ShortLongDicomCompare.pl` / `Posda::DiffDicom`)

- The diff compares leaf elements by path. An empty sequence item has no leaves, so creating
  or removing one never shows up.
- "Only in from file" in the **short** report prints only the first element (sorted) of each
  pattern. A file that lost `[2]`–`[7]` shows only `[2]`; one line does not mean one element.
- For item deletes that are all trailing, items after the deleted ones shift down, so the
  first index under "Only in from file" equals the number of items left — provided every
  original item carried the element shown. A deleted real ROI shows up as its own ROI
  Number / Name / Generation Algorithm lines.
- The report's `short_file_id` / `long_file_id` are the stored report text files (identical
  reports are stored once), not the edited DICOM files. `DifferenceReportByEditId` only
  counts files per report pair. To find the files behind a report, join
  `dicom_edit_compare.from_file_digest` to `file.digest` for that `subprocess_invocation_id`
  and `short_report_file_id`.

### Phasing

1. **Internal reference checks + edits.** *Rules done:* `posda/rtstruct.py` and
   `CheckRtStructRois.py` implement every rule below, plus the unreadable-file guard;
   `tests/posda/test_rtstruct.py` covers each rule, the conformant cases that must stay clean,
   non-DICOM responses, descending order, grouping and the sheet layout. Run from the "Check RT
   Structure Set ROIs" button, after "Link RT Data".

   Every rule enforces a PS3.3 requirement, checked against the 2026d edition and cited in
   each rule's docstring:

   | Rule | PS3.3 basis | Action |
   |---|---|---|
   | Structure Set ROI / Referenced FOR / ROI Contour / RT ROI Observations Sequence present with no items | C.8.8.5, C.8.8.6, C.8.8.8, "One or more Items are permitted" | delete the whole sequence; the planner also deletes the whole sequence when item deletes would empty it |
   | Structure Set ROI item without ROI Number | C.8.8.5, Type 1 | delete if empty or FOR-only, else report |
   | Duplicate ROI Numbers | C.8.8.5, "shall be unique within the Structure Set" | report |
   | ROI without a Referenced Frame of Reference UID | C.8.8.5, Type 1 | report |
   | ROI FOR not listed in, or listed more than once in, the Referenced Frame of Reference Sequence | C.8.8.5.1, "once and only once" | report |
   | ROI Contour item referencing an undeclared ROI — *redundant* (every contour also present in a declared ROI) | C.8.8.6, Referenced ROI Number "uniquely identifies the referenced ROI described in the Structure Set ROI Sequence" | delete |
   | Same, *unique* (holds contours found nowhere else) | same | report only — may mean an ROI was dropped from the declarations by mistake; the fix would be restoring the declaration |
   | RT ROI Observation referencing an undeclared ROI | C.8.8.8, same wording | delete, unless the ROI has a unique contour item |
   | RT Related ROI referencing an undeclared ROI | C.8.8.8, same wording | report |
   | Missing Referenced ROI Number (contour item, observation) | C.8.8.6 / C.8.8.8, Type 1 | report |
   | Missing or duplicate Observation Number | C.8.8.8, Type 1, "shall be unique within the RT ROI Observations Sequence" | report |
   | CLOSEDPLANAR_XOR mixed with other geometric types in one ROI | C.8.8.6, "all Contours of that ROI shall be of the same type" | report |

   *Not rules* — conformant in the current standard:
   - A missing Structure Set ROI, Referenced Frame of Reference, ROI Contour, RT ROI
     Observations or RT Related ROI Sequence. All are Type 3. Older editions had several as
     Type 1, so older validators may still flag them. *Present but empty* is a finding (see
     the table).
   - A declared ROI with no ROI Contour item or no RT ROI Observation. Nothing requires one
     item per declared ROI.
   - Several ROI Contour items for one ROI. The standard doesn't address it.
   - Mixed geometric types other than CLOSEDPLANAR_XOR (e.g. CLOSED_PLANAR with POINT). The
     Perl `NumRois` check calls this suspicious, but the standard allows it.

   *Implemented as specified, with these details:*
   - Contours compare by geometric type and points (floats), not by image references.
   - An ROI Contour item with no contours counts as redundant.
   - ROI Numbers compare as integers, so `011` matches `11`.
   - An observation for an undeclared ROI is report-only when that ROI Number also has a
     *unique* contour item. Its label and interpreted type are what restoring the declaration
     needs.
   - Items with no Referenced ROI Number are report-only.
   - One series' deletes can span several sequences. Each sequence is ordered from its
     highest index down; the sequences don't affect each other's indices.

   Tests: synthetic pydicom unit tests (detection, redundant/unique split, descending-index
   ordering); apply generated edits through the real `Posda::Dataset` delete via the
   `Posda::Config` stub above, to confirm ordering on the code that will apply them.
2. **Contour-level checks:** point counts vs Number of Contour Points (C.8.8.6, "Number of
   points (triplets) in Contour Data"), planarity of CLOSED_PLANAR contours (C.8.8.6, "All
   points in Contour Data (3006,0050) shall be coplanar"), contours with no image reference,
   contour image refs outside the declared volume (ports `UnlinkedClosedPlanar`,
   `InternalLinkages`). Check each against the standard before adding it, as in phase 1.
   Contours with no image reference are conformant: Contour Image Sequence (3006,0016) is
   Type 3, and C.8.8.6.4 says it "is not required to be present" (contours are placed by
   patient coordinates within the ROI's Frame of Reference). Flagging them is curation
   policy, not conformance. Contours not tied to a declared ROI are a different case,
   non-conformant and covered by phase 1.
3. **Cross-file checks using the DB:** referenced images exist, FOR matches the images,
   contour z vs slice geometry (ports `FrameOfRefExternal`, `VolumeFilesInPosda`,
   `FrameOfReferenceMatches`; `SubProcessStructLinkageReport.pl`'s math implements
   `PointsWithinVolume`). After this `CheckStructLinkagesTpId.pl` can retire.
4. **Per-file detail mode** replacing `DumpLinkages.pl` / `BackgroundSingleRtLinkageDetailReports.pl`.

### Cautions

- Ship phase 1 on its own; don't block it on a full port.
- `CheckStructLinkagesTpId.pl` calls itself a "test version" — phases 2–3 need confirmation
  that its checks are the right spec (see open questions).

## Ideas / TODO

- [ ] **RTSTRUCT ROI checker, phase 1** — model + internal reference rules + `BackgroundEditTp` edit generation (see "RTSTRUCT ROI checker — plan"). All phase 1 rules done, each checked against PS3.3; remaining: `.row`/button (below) and committing.
- [x] `CheckRtStructRois.row` + "Check RT Structure Set ROIs" button after "Link RT Data" (needs `SyncAllSpreadsheetOps` on deploy, like any new `.row`).
- [ ] Guard `LinkageChecker.load_dataset` (or its callers) against non-DICOM responses, as `rtstruct.dataset_problem()` does — today the linkage checkers would report such files as having no problems (see "Never treat an unreadable file as clean").
- [ ] `BackgroundProcess._close_reports()`: keep uploading the remaining reports when one upload fails, and report the failure (see "Report upload pitfalls").
- [ ] **Close the `StructureSetROISequence` FOR-fixup gap in `fix_rtstruct`** (FixLinkages.py) — clearest, lowest-risk win identified in the relink comparison above. Iterate the ROI sequence itself, keyed on ROI Number, not ROI Contour item positions (the StructFixer bug).
- [ ] Add geometry-based (Z-slot) contour-to-image mapping to `fix_rtstruct`, replacing the lexicographic-UID fallback — the most consequential correctness gap found.
- [ ] Add overlap/slice-spacing validation to `fix_rtstruct`, mirroring `SubProcessRelinkStruct.pl`'s hard-abort-on-overlap check.
- [ ] Port `CheckStructLinkagesTpId.pl`'s internal-consistency checks into the RTSTRUCT ROI checker (phases 2–3), not `RTLinkageChecker`. Make the NumRois → SopsInVol → InternalLinkages/FrameOfRefExternal → VolumeFilesInPosda → FrameOfReferenceMatches data dependencies explicit (see deep-dive above); read structure from the DICOM rather than the DB tables; explicitly drop `PointsWithinVolume` (unimplemented stub) rather than porting it as a real check.
- [ ] Port `SubProcessStructLinkageReport.pl`'s geometric contour-to-image Z-matching logic into the ROI checker (phase 3) — candidate implementation for the still-unimplemented `PointsWithinVolume` check.
- [ ] Port `DumpLinkages.pl`'s per-file linkage/geometry logic as the ROI checker's per-file detail mode (phase 4; backs the live `BackgroundSingleRtLinkageDetailReports.pl` UI report — reclassified from retirement candidate, see above).
- [ ] StructFixer fail-open guards — return 0 from `LinkStructSet` when no image passes the axial check, and on an undefined `$closest_z` (see "StructFixer.pm bugs fixed"). Separate from the tolerance fix because it turns some former "OK" results into "Failed".
- [ ] Decide whether StructFixer should keep writing the image SOP class into the study-level `(3006,0012)[n](0008,1150)`.
- [ ] Verify RTDOSE/RTPLAN collection-site-patient cross-checks aren't lost vs. `BackgroundDoseLinkageCheck.pl` / `BackgroundPlanLinkageCheck.pl`
- [ ] Plan retirement of the non-Tp Perl scripts + their `.row` files once parity is confirmed
- [ ] **Re-enable candidate suggestion and the Fix script**, when ready: uncomment `suggest_missing_ref_candidates()`/`suggest_relink_candidates()` in all three checkers (`CheckLinkages.py`, `CheckSegLinkages.py`, `CheckRtLinkages.py`), the RTSTRUCT relink-worklist block in `CheckRtLinkages.py`, and the candidate-suggestion columns in `REFERENCE_REPORT_HEADER`/`FOR_MISMATCH_HEADER`/`reference_to_row()` (linkage.py) — all commented out (not deleted) for easy restoration, see "Candidate suggestion and the Fix script" and "Report output" notes above.
