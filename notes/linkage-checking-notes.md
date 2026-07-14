# Linkage Checking — Working Notes

Team-shared planning notes for the linkage-checking feature set.

## Files involved

| File | Role |
|---|---|
| [posda/posdatools/python/posda/linkage.py](../posda/posdatools/python/posda/linkage.py) | `LinkageChecker` base class — all shared logic (DB queries, DICOM walking, candidate suggestion, report writers) |
| [posda/posdatools/Posda/bin/CheckLinkages.py](../posda/posdatools/Posda/bin/CheckLinkages.py) | `GeneralLinkageChecker` — all modalities, plus UID anomaly detection (dup SOPs, cross-category overlaps) |
| [posda/posdatools/Posda/bin/CheckSegLinkages.py](../posda/posdatools/Posda/bin/CheckSegLinkages.py) | `SegLinkageChecker` — SEG files only, scans `ReferencedSeriesSequence` |
| [posda/posdatools/Posda/bin/CheckRtLinkages.py](../posda/posdatools/Posda/bin/CheckRtLinkages.py) | `RTLinkageChecker` — RTSTRUCT/RTPLAN/RTDOSE/RTIMAGE, scans RT-specific ref sequences, also builds RTSTRUCT relink worklist |
| [posda/posdatools/Posda/bin/FixLinkages.py](../posda/posdatools/Posda/bin/FixLinkages.py) | Standalone fixer — reads a `Relink_Worklist` CSV, rewrites RTSTRUCT/SEG files to point at a corrected target series, writes to `$POSDA_CACHE_ROOT/edits/<uuid>/` for review before import |

## Architecture

- `LinkageChecker` (linkage.py) is the shared base. Subclasses set `reference_sequences`
  to restrict which top-level DICOM sequences get walked:
  - `None` (CheckLinkages/general) → scan all nested UID tags
  - `REFERENCE_SEQUENCES_SEG` → just `ReferencedSeriesSequence`
  - `REFERENCE_SEQUENCES_RT` → FOR/structure-set/plan/dose reference sequences
- Common pipeline across all three checkers:
  1. `get_activity_files()` — pull latest activity_timepoint's DICOM files from DB
  2. `build_uid_context()` — build SOP/series/study/FOR UID sets + SOP→FOR / SOP→series maps
  3. `find_missing_references()` — walk each file's dataset, flag missing refs + FOR mismatches
  4. `annotate_missing_refs()` — look up "missing" refs globally across all of Posda (not just this activity)
  5. `suggest_missing_ref_candidates()` / `suggest_relink_candidates()` — tiered heuristics to propose a fix target
  6. `create_split_reference_reports()` / `create_for_mismatch_report()` / `create_for_repair_reports()` / `create_edit_skeleton()` — CSV report generation consumed by `BackgroundEditTp`

- Fix path is separate: `CheckRtLinkages.py` builds a `Relink_Worklist` CSV (RTSTRUCT only —
  FOR-only mismatches for RTPLAN/RTDOSE/RTIMAGE are handled via tag-edit CSVs, not structural
  relink). `FixLinkages.py` consumes that worklist and does the actual DICOM rewrite
  (`fix_rtstruct` / `fix_seg`), diffing before/after with `ShortLongDicomCompare.pl`.

## Candidate-suggestion tiers (for reference)

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

### Functional gap — SEG relink path looks unreachable

`CheckSegLinkages.py` has `suggest_missing_ref_candidates()` and
`suggest_relink_candidates()` commented out
([CheckSegLinkages.py:47-48](../posda/posdatools/Posda/bin/CheckSegLinkages.py#L47-L48)),
and unlike `CheckRtLinkages.py` it never calls `create_relink_report()`. But
`FixLinkages.py` has a fully implemented `fix_seg` fixer registered in `_FIXERS`. The
relink worklist that would drive `fix_seg` is only ever generated by
`CheckRtLinkages.py` (RTSTRUCT-only) — so `fix_seg` currently has no automatic path to
being invoked unless someone hand-builds a `Relink_Worklist` CSV.

Status: needs a decision — confirm intentional vs. finish the SEG relink-suggestion wiring.

### Architecture — duplicated `run()` pipeline across the three checkers

`CheckLinkages.py`, `CheckSegLinkages.py`, `CheckRtLinkages.py` each hand-roll the same
divider/print/scan/annotate/suggest/report sequence. Template-method candidate: base class
owns the pipeline shape, subclasses override "get source files" + a couple of hooks
(e.g. RT's relink-worklist step). Would shrink each script to just its modality-specific
bits and make it obvious when a step (like SEG's missing relink step, above) is skipped
vs. simply forgotten.

Status: idea only, no urgency — revisit after the SEG gap and legacy port are settled.

### Maintainability — no test coverage for the candidate-suggestion tiers

`suggest_missing_ref_candidates`'s 6-tier logic and `suggest_relink_candidates`'s
same-study/same-activity fallback are the most intricate, most likely to silently regress
code in the file. Worth a handful of unit tests with synthetic UID sets before this becomes
the code everyone's afraid to touch.

Status: idea only.

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
| `Posda/bin/SubProcess/SubProcessStructLinkageReport.pl` | Not fully read (355 lines) — likely feeds detail reports, overlaps with internal-consistency checks. | **Follow-up needed.** |
| `Posda/bin/BackgroundSingleRtLinkageDetailReports.pl` | Not fully read (106 lines) — likely UI drill-down companion to bulk struct-linkage reports. | **Follow-up needed.** |

### Retirement candidates (superseded, pre-timepoint, stub, or out-of-scope)

Pre-timepoint duplicates of scripts above (superseded by the `Tp`/timepoint-aware versions):
- `Posda/bin/TestStructFixer.pl` (→ `TestStructFixerTp.pl`)
- `Posda/bin/BackgroundFixStructLinkages.pl` (→ `BackgroundFixStructLinkagesTp.pl`)
- `Posda/bin/CheckStructLinkages.pl` (→ `CheckStructLinkagesTpId.pl`)
- `Posda/bin/PopulateFileRoiImageLinkages.pl` (→ `PopulateFileRoiImageLinkagesByTimepoint.pl`)

Pre-DB / pre-`StructFixer.pm` duplicate algorithms, no DB or timepoint concept at all:
- `Posda/bin/FixRtStruct.pl`, `Posda/bin/FixRtStruct1.pl` — filesystem-only nearest-Z remap, near-duplicates of each other
- `Posda/bin/contrib/FixBadlyAnonymizedCtsAndStruct.pl` — one-off anonymization-migration variant of same algorithm
- `Posda/bin/CheckRtdoseLinkagesIntake.pl` — ad hoc intake-era script, reads raw DICOM tags directly instead of DB linkage tables

Stub / debug / tangential (not core linkage-checking logic):
- `Posda/bin/BackgroundStructLinkageCheck.pl` — unimplemented stub ("Checking Not currently implemented")
- `Posda/bin/DumpLinkages.pl`, `Posda/bin/SummarizeStructLinkagesByFileId.pl` — ad hoc debug/inspection tools
- `Posda/bin/SubProcess/SubProcessCloneStruct.pl` — file-management (clone/copy), not linkage logic
- `Posda/bin/FixForRtStructWithPixelOrFor.pl`, `posdatools/bin/FixMaastroStructs.pl` — DICOM-conformance cleanup, unrelated to reference linkage
- `Posda/bin/BulkHashStructUids.pl` — anonymization tool, touches the same UID elements but isn't linkage checking

`.row` UI descriptors to retire alongside their Perl scripts (confirmed legacy/non-Tp):
`BackgroundFixRtstruct.row`, `CheckStructLinkagesByCollectionSite.row`
(vs. currently-wired `BackgroundFixRtstructTp.row`, `CheckStructLinkagesTp.row`, both tagged `activity_timepoints`)

### Open questions / things to dig into next

- Does `FixLinkages.py`'s `fix_rtstruct` match `StructFixer.pm`'s nearest-Z algorithm, or should it adopt `SubProcessRelinkStruct.pl`'s geometry/overlap-aware approach instead?
- Read `SubProcessStructLinkageReport.pl` and `BackgroundSingleRtLinkageDetailReports.pl` in full — determine if they duplicate `CheckStructLinkagesTpId.pl` or add something new.
- Does `BackgroundFixStructLinkagesTp.pl`'s `dicom_edit_compare_disposition`/`dicom_edit_compare_fixed` DB tracking have an equivalent in the new Python accept/reject flow, or does that state live only in email buttons today?
- Scope out porting `CheckStructLinkagesTpId.pl`'s internal ROI/contour checks into `RTLinkageChecker` (new methods needed: NumRois, SopsInVol, SopsLinkedToRoi, InternalLinkages, FrameOfRefExternal, UnlinkedClosedPlanar, etc.)

## Ideas / TODO

- Port `CheckStructLinkagesTpId.pl` internal-consistency checks into `RTLinkageChecker`
- Verify RTDOSE/RTPLAN collection-site-patient cross-checks aren't lost vs. `BackgroundDoseLinkageCheck.pl` / `BackgroundPlanLinkageCheck.pl`
- Plan retirement of the non-Tp Perl scripts + their `.row` files once parity is confirmed
