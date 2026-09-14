# Ingest defect fixes (`POSDA_INGEST_FIX_*`)

The Python ingest pipeline (`python/posda/ingest/`) reproduces the Perl
fast-file-processor bug for bug. That is deliberate: it is what lets the two
be compared by exact row diff, and that comparison is what makes the cutover
safe.

Twelve defects were found while porting, all confirmed against a real
database rather than inferred. Ten of them are reproduced by default and
corrected only when you ask, through the flags below. Two are fixed
outright, with no flag: `RtPatientSetup`, because reproducing it means
reproducing a crash, and the lookup-table insert race, because reproducing
it means duplicating rows under concurrency (see "Always on" below).

One flag is not a defect correction at all: `ATOMIC_IMPORT` changes how a
*failed* import lands, wrapping each file in a transaction.

## Sequencing

**Turn these on only after the Python workers have replaced the Perl ones.**
While both are live, enabling a fix makes the two implementations disagree
and the differential harness stops being a useful signal. With every flag
off, `tools/verify_ingest.py` reports zero differences.

Enable them **one at a time**. Five change row counts or values in tables
that analyst queries read.

## Setting a flag

Each is an environment variable on the worker, named
`POSDA_INGEST_FIX_<NAME>`, accepting `1`, `true`, `yes` or `on`
(case-insensitive). Anything else, including unset, is off.

Set it on the **workers**, not on `posda-fast-file-process` — that role only
fills the queue and never parses a file. `LOAD_LARGE_VALUES` is the one
exception worth calling out: it affects both `file-worker` and
`pixel-worker`, and the pixel worker already parses without a size limit.

```yaml
# config/docker-compose.yaml
posda-file-worker:
    command: file-worker-py
    environment:
        - POSDA_INGEST_FIX_XFR_STX=1
```

Under Kubernetes the flags live in the `posda-ingest-config` ConfigMap,
which all three Deployments read; see `k8s/README.md`.

Flags are read once at import, so a worker must be restarted to pick up a
change. `posda.ingest.fixes.ACTIVE.enabled_names()` reports what is on.

## Safe: columns that are unconditionally NULL today

Nothing reads a value from these columns now, because nothing has ever been
written to them. Turning these on adds data without changing any existing
row or count.

| Flag | Column | Why it is empty |
|---|---|---|
| `XFR_STX` | `dicom_file.xfr_stx` | `Posda::NewTry` declares `$xfr_stx` and never assigns it. 0 of 1256 rows populated. |
| `ORIGINAL_SPECIALIZED_SOP_CLASS` | `file_sop_common.original_specialized_sop_class` | `DicomIod` reads (0008,001b) into key `orig_spec_sop_class`, then passes `$parms{original_specialized_sop_class}` — never set. 0 of 1256. |
| `DOSE_NORMALIZATION_POINT` | `rt_dose.rt_dose_normalization_point` | `RTDose` reads into `normalization_point`, then passes `$parms{normalizaton_point}` — missing an "i". |

## Changes row counts

| Flag | Effect | Why |
|---|---|---|
| `WINDOW_LEVEL_DUPLICATION` | Fewer `file_win_lev` rows | `WindowLevel`'s explanation branch nests two loops that both use `$i`; the inner shadows the outer, so N window explanations produce N² rows instead of N. Only affects files carrying (0028,1055). |
| `LOAD_LARGE_VALUES` | Changes `image`, `unique_pixel_data`, `pixel_location`; **costs memory** | `skip_large => 256` silently NULLs any non-SQ value over 256 bytes. Because it strips the pixel element's value it also disables `ImagePixel`'s deduplication entirely, so those two tables are empty and every file gets its own `image` row. Lifting the limit revives dedup and loads pixel data into memory. |
| `ELEMENTAL_COMPOSITION` | Populates `roi_elemental_composition` | Unreachable twice over: `RtRoiObservations` walks (3006,00a0), the related-observations sequence, with the index from the (3006,00b0) physical-properties loop; and its insert calls `currval` on a sequence name that does not exist, the real one carrying the schema's "phyical" typo. |
| `FRACTION_RELATED_DOSE` | Populates `fraction_related_dose`, removes two complaints per item from `dicom_process_errors` | `RtFractionScheme` passes the fraction *group* parameter table to `GetAttrs` in that loop, so neither UID is read and both guards fire. |
| `BEAM_GENERAL_ACCESSORY` | Populates `beam_general_accessory` | The INSERT's column list reads `general_accessory_id text` — a stray type name — making the statement a syntax error. Under DBI's default `RaiseError=0` that prints and carries on. |

## Changes values

| Flag | Effect |
|---|---|
| `PRESCRIPTION_ORGAN_AT_RISK_TAGS` | `RtPrescription` reads (300a,002b) into organ-at-risk limit dose, maximum dose *and* overdose volume fraction alike, so the last two currently carry the limit dose. The flag reads (300a,002c) and (300a,002d) instead. Existing `rt_prescription_dose_ref` rows keep the wrong values; only new rows differ. |

## Changes failure behaviour: `ATOMIC_IMPORT`

The Perl runs every statement under DBI's default AutoCommit. A handler
that dies partway leaves the rows it already wrote — and because
`dicom_file.is_dicom_file` is committed before the handlers run, the failed
file drops out of the daemon's replenish query and sits partial forever.
Nothing marks it failed, and re-processing it by hand duplicates rows,
since most module tables carry no unique constraints.

With `ATOMIC_IMPORT` on, each file's import is one transaction:

- A **successful** import commits exactly the rows it would have written
  anyway; the flag changes nothing.
- A **failed** import rolls back completely — including the
  `is_dicom_file` update. To keep the daemon from re-queueing the file into
  an infinite retry loop, a follow-up step then records the
  `dicom_process_errors` accumulated before the crash plus an
  `import failed, rows rolled back: ...` row naming the exception, and
  clears `file.ready_to_process`.

To retry a file after fixing the cause, set `ready_to_process` back to
true; the daemon picks it up on its next refill. Rows in
`dicom_file_errors` (metaheader complaints) are not preserved across the
rollback; they regenerate on retry.

This flag only changes what a failure leaves behind, so the differential
harness stays at zero differences as long as the corpus imports cleanly.

## Always on: lookup upserts (requires a schema migration)

The shared lookup tables `slope_intercept`, `window_level` and
`unique_pixel_data` are written with `ON CONFLICT` rather than the Perl's
check-then-insert. Under the production five workers, check-then-insert
races: two workers can miss the same row and both insert it. In the dev
database `slope_intercept` held 4 rows of which 1 was distinct, and
`window_level` 5 of which 3 were. Single-threaded — which is how the
differential harness runs — the two approaches produce identical rows, so
this is not a flag.

The upserts require the unique indexes from the
`database/migrations/posda_files/20260913_ingest_lookup_unique.sql`
migration, which deduplicates the existing rows and remaps references
before deleting. Apply it (`./migrate up posda_files`) **before** running
the Python workers: without the indexes, every `ON CONFLICT` statement
fails outright. `NULLS NOT DISTINCT` is load-bearing there — `si_units`
and `win_lev_desc` are NULL on most rows, and under the default the
constraint would prevent nothing. It needs PostgreSQL 15 or later.

## Always on: `RtPatientSetup`

This handler crashes the Perl, so there is no working behaviour to preserve.
Two independent fatal paths, both confirmed by running it:

- a `SetupDeviceSequence` reaches the signature `(300a,1b4)[$j](300a,01ba)`,
  three hex digits where four are required, and `ExtractElementBySig` dies
  with `Sig ((300a,1b4)[0](300a,01ba)) didn't match`;
- a `FixationDeviceSequence` calls `$ds->prepare(...)` on a
  `Posda::Dataset`, which has no such method.

Handlers run without `eval`, so either one kills the whole file import:
rows already written stay behind under autocommit, `dicom_process_errors` is
never written, and `RtFractionScheme` and `RtBeams` never run for that file.
**Any RT Plan carrying setup devices or fixation devices fails to import
under the Perl today.** Worth checking your archive for these independently
of the port.

Two further defects in the same handler are corrected alongside: it wrote to
`rt_plan_fixation_device` (really `rt_plan_setup_fixation_device`), and it
nested the shielding device, setup device and respiratory motion loops
inside the setup-image loop, so those rows appeared once per setup image and
not at all without one.

## Verifying a fix

`tools/verify_ingest.py --corpus DIR` runs the Perl and Python pipelines over
the same files into two throwaway copies of the schema and diffs every
populated table. With flags off it should report zero differences; with a
flag on, the differences it reports are exactly that flag's effect, which is
a good way to see the blast radius before enabling it in production.
