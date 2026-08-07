-- Test data for Posda Dataset / Recordset Release Module
-- Aligned to add_dataset_module_tables.sql as currently modeled.
--
-- Release-cycle coverage. Datasets 1-2 are the steady-state fixture; a few
-- recordsets are pushed off that baseline so the mid-cycle states the UI
-- branches on actually occur somewhere:
--
--   ds 1 / rs 1  open draft, QC in progress (mixed statuses)
--   ds 1 / rs 2  open draft, QC stale                        -> blocked
--   ds 1 / rs 3  FROZEN v2, not bundled into any dataset release
--                (the fan-in signal: "ready to cut a release")
--   ds 1 / rs 4  open draft, QC complete                     -> publishable
--   ds 2 / rs 5  open draft, partial (25%) QC, slice UNCLAIMED -> pickup queue
--   ds 2 / rs 6  open draft, only a cancelled review         -> reads as "no QC"
--   ds 3 / rs 7  open draft, never released                  -> first cycle
--   ds 3 / rs 8  frozen v1, dataset release 3 is still 'draft' and does not
--                contain it yet                              -> assembling
--   ds 4 / rs 9  bare: no draft, no release, no dataset_release at all
--
-- dataset_release.release_status covers all four values: 1 = live (its
-- WordPress transfer succeeded), 2 = released, 3 = draft. Retracted is not
-- seeded -- flip one by hand to check the "latest falls back" rule.
--
-- Transfer statuses on dataset release 1 are spread across draft/queued/
-- in_progress/success/failed rather than all 'draft'.

BEGIN;

-- -----------------------------------------------------------------------------
-- Lookup tables
-- -----------------------------------------------------------------------------

INSERT INTO public.dataset_type (dataset_type_id, dataset_type_name) VALUES
    (1, 'Collection'),
    (2, 'Analysis Result');
SELECT setval(pg_get_serial_sequence('public.dataset_type', 'dataset_type_id'), COALESCE(MAX(dataset_type_id), 0), true) FROM public.dataset_type;

INSERT INTO public.dataset_relation_type (relation_type_id, forward_label, reverse_label) VALUES
    (1, 'isDerivedFrom', 'isSourceOf');
SELECT setval(pg_get_serial_sequence('public.dataset_relation_type', 'relation_type_id'), COALESCE(MAX(relation_type_id), 0), true) FROM public.dataset_relation_type;

INSERT INTO public.recordset_type (recordset_type_id, recordset_type_name) VALUES
    (1, 'Radiology Images'),
    (2, 'Histopathology Images'),
    (3, 'Image Annotations'),
    (4, 'Clinical Data'),
    (5, 'Other');
SELECT setval(pg_get_serial_sequence('public.recordset_type', 'recordset_type_id'), COALESCE(MAX(recordset_type_id), 0), true) FROM public.recordset_type;

INSERT INTO public.transfer_mode (transfer_mode_id, transfer_mode_name) VALUES
    (1, 'single dataset'),
    (2, 'grouped bundle'),
    (3, 'clinical update');
SELECT setval(pg_get_serial_sequence('public.transfer_mode', 'transfer_mode_id'), COALESCE(MAX(transfer_mode_id), 0), true) FROM public.transfer_mode;

INSERT INTO public.recordset_license (license_id, license_name, license_label, license_url, is_public_access) VALUES
    (1, 'Creative Commons Attribution 3.0 Unported', 'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/', true),
    (2, 'Creative Commons Attribution 4.0 International', 'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/', true),
    (3, 'Creative Commons Attribution-NonCommercial 4.0 International', 'CC BY-NC 4.0', 'https://creativecommons.org/licenses/by-nc/4.0/', true),
    (4, 'TCIA Limited Access', 'TCIA Limited', 'https://www.cancerimagingarchive.net/nih-controlled-data-access-policy/', false);
SELECT setval(pg_get_serial_sequence('public.recordset_license', 'license_id'), COALESCE(MAX(license_id), 0), true) FROM public.recordset_license;

INSERT INTO public.transfer_destination (destination_id, destination_name, destination_abbr) VALUES
    (1, 'Imaging Data Commons', 'idc'),
    (2, 'General Commons', 'gc'),
    (3, 'WordPress', 'wp'),
    (4, 'Aspera Faspex', 'asp'),
    (5, 'NBIA', 'nbia');
SELECT setval(pg_get_serial_sequence('public.transfer_destination', 'destination_id'), COALESCE(MAX(destination_id), 0), true) FROM public.transfer_destination;

-- -----------------------------------------------------------------------------
-- Dataset and dataset relationship test data
-- -----------------------------------------------------------------------------

INSERT INTO public.dataset (
    dataset_id,
    dataset_name,
    dataset_type_id,
    dataset_doi,
    active,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    (
        1,
        'RIDER-LUNG-CT',
        1,
        '10.7937/k9/tcia.2015.u1x8a5nr',
        true,
        NOW(),
        0,
        NOW(),
        0
    ),
    (
        2,
        'RIDER-LUNGCT-SEG',
        2,
        '10.7937/tcia.2020.jit9grk8',
        true,
        NOW(),
        0,
        NOW(),
        0
    ),
    -- Dataset 3 is mid-first-cycle: a draft dataset release being assembled.
    (
        3,
        'PSEUDO-MIDI-TEST',
        1,
        '10.7937/tcia.test.pseudo.midi',
        true,
        NOW(),
        0,
        NOW(),
        0
    ),
    -- Dataset 4 is bare: a recordset but nothing started, and no
    -- dataset_release at all. Keeps the "no release yet" path covered.
    (
        4,
        'EMPTY-CYCLE-TEST',
        1,
        '10.7937/tcia.test.empty.cycle',
        true,
        NOW(),
        0,
        NOW(),
        0
    );
SELECT setval(pg_get_serial_sequence('public.dataset', 'dataset_id'), COALESCE(MAX(dataset_id), 0), true) FROM public.dataset;

-- Dataset 2 isDerivedFrom Dataset 1.
-- The reverse relation is derived from dataset_relation_type.reverse_label as isSourceOf.
INSERT INTO public.dataset_relation (dataset_id, related_dataset_id, relation_type_id) VALUES
    (2, 1, 1);

-- -----------------------------------------------------------------------------
-- Recordsets and destination defaults
-- -----------------------------------------------------------------------------

INSERT INTO public.recordset (
    recordset_id,
    recordset_name,
    recordset_type_id,
    dataset_id,
    license_id,
    recordset_doi,
    active,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    (1, 'Radiology 01 Public', 1, 1, 2, null, true, NOW(), 0, NOW(), 0),
    (2, 'Radiology 02 Public', 1, 1, 2, null, true, NOW(), 0, NOW(), 0),
    (3, 'Radiology 03 Limited', 1, 1, 4, null, true, NOW(), 0, NOW(), 0),
    (4, 'Clinical 01 Public', 4, 1, 2, null, true, NOW(), 0, NOW(), 0),
    (5, 'Image Annotations 01 Public', 3, 2, 2, null, true, NOW(), 0, NOW(), 0),
    (6, 'Image Annotations 02 Limited', 3, 2, 4, null, true, NOW(), 0, NOW(), 0),
    -- Dataset 3: first-cycle recordset (never released) and a frozen one.
    (7, 'Radiology 04 First Cycle', 1, 3, 2, null, true, NOW(), 0, NOW(), 0),
    (8, 'Radiology 05 Frozen', 1, 3, 2, null, true, NOW(), 0, NOW(), 0),
    -- Dataset 4: nothing started at all.
    (9, 'Radiology 06 Untouched', 1, 4, 2, null, true, NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.recordset', 'recordset_id'), COALESCE(MAX(recordset_id), 0), true) FROM public.recordset;

-- transfer_mode_id is hardcoded per destination in the frontend (hidden from
-- the user): idc/gc/nbia -> grouped bundle (2), wp/asp -> single dataset (1).
INSERT INTO public.recordset_destination (recordset_id, destination_id, default_display, transfer_mode_id) VALUES
    (1, 1, true,  2), -- Radiology public: IDC default, grouped bundle
    (1, 5, false, 2), -- Radiology public: NBIA alternative, grouped bundle
    (2, 1, true,  2), -- Radiology public: IDC default, grouped bundle
    (2, 5, false, 2), -- Radiology public: NBIA alternative, grouped bundle
    (3, 2, true,  2), -- Radiology limited: General Commons default, grouped bundle
    (4, 3, true,  1), -- Clinical public: WordPress default, single dataset
    (4, 1, false, 2), -- Clinical public: IDC alternative, grouped bundle
    (5, 1, true,  2), -- Annotation public: IDC default, grouped bundle
    (6, 2, true,  2), -- Annotation limited: General Commons default, grouped bundle
    (7, 1, true,  2), -- Pseudo-MIDI first cycle: IDC default, grouped bundle
    (8, 1, true,  2), -- Pseudo-MIDI frozen: IDC default, grouped bundle
    (9, 1, true,  2); -- Empty cycle: IDC default, grouped bundle

-- -----------------------------------------------------------------------------
-- Immutable recordset releases and file membership
-- Assumes public.file contains file_id values 1 through 26.
-- -----------------------------------------------------------------------------

INSERT INTO public.recordset_release (
    recordset_release_id,
    recordset_id,
    release_number,
    release_date,
    release_notes,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    (1, 1, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0),
    (2, 2, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0),
    (3, 3, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0),
    (4, 4, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0),
    (5, 5, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0),
    (6, 6, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0),
    -- Recordset 3 v2: frozen but deliberately NOT added to dataset release 1,
    -- so the dataset has a recordset ready to bundle into a new release.
    (7, 3, 2, NOW(), 'Second Release - awaiting dataset release', NOW(), 0, NOW(), 0),
    -- Dataset 3's frozen recordset. Dataset 3 has no dataset_release at all.
    (8, 8, 1, NOW(), 'Initial Release', NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.recordset_release', 'recordset_release_id'), COALESCE(MAX(recordset_release_id), 0), true) FROM public.recordset_release;

INSERT INTO public.recordset_release_file (recordset_release_id, file_id) VALUES
    (1, 1),  (1, 2),  (1, 3),  (1, 4),  (1, 5),
    (2, 6),  (2, 7),  (2, 8),  (2, 9),  (2, 10),
    (3, 11), (3, 12), (3, 13), (3, 14), (3, 15),
    (4, 16),
    (5, 17), (5, 18), (5, 19), (5, 20), (5, 21),
    (6, 22), (6, 23), (6, 24), (6, 25), (6, 26),
    -- v2 of recordset 3 drops file 15 and adds file 16, so a diff against v1
    -- is non-empty.
    (7, 11), (7, 12), (7, 13), (7, 14), (7, 16),
    (8, 17), (8, 18), (8, 19), (8, 20), (8, 21);

-- -----------------------------------------------------------------------------
-- Editable drafts cloned from current immutable releases
-- -----------------------------------------------------------------------------

INSERT INTO public.recordset_draft (
    recordset_draft_id,
    recordset_id,
    draft_name,
    draft_status,
    draft_notes,
    cloned_from_release_id,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    (1, 1, 'Version 2 Draft', 'open', null, 1, NOW(), 0, NOW(), 0),
    (2, 2, 'Version 2 Draft', 'open', null, 2, NOW(), 0, NOW(), 0),
    -- Draft 3 was published as recordset release 7, so recordset 3 has no
    -- open draft: its cycle is parked at "frozen, awaiting dataset release".
    (3, 3, 'Version 2 Draft', 'published', null, 3, NOW(), 0, NOW(), 0),
    (4, 4, 'Version 2 Draft', 'open', null, 4, NOW(), 0, NOW(), 0),
    (5, 5, 'Version 2 Draft', 'open', null, 5, NOW(), 0, NOW(), 0),
    (6, 6, 'Version 2 Draft', 'open', null, 6, NOW(), 0, NOW(), 0),
    -- First cycle: no cloned_from_release_id because nothing was ever frozen.
    (7, 7, 'Initial Draft', 'open', 'First cycle - never released', null, NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.recordset_draft', 'recordset_draft_id'), COALESCE(MAX(recordset_draft_id), 0), true) FROM public.recordset_draft;

INSERT INTO public.recordset_draft_file (recordset_draft_id, file_id) VALUES
    (1, 1),  (1, 2),  (1, 3),  (1, 4),  (1, 5),
    (2, 6),  (2, 7),  (2, 8),  (2, 9),  (2, 10),
    (3, 11), (3, 12), (3, 13), (3, 14), (3, 16),
    (4, 16),
    (5, 17), (5, 18), (5, 19), (5, 20), (5, 21),
    (6, 22), (6, 23), (6, 24), (6, 25), (6, 26),
    (7, 22), (7, 23), (7, 24);

-- -----------------------------------------------------------------------------
-- Dataset releases composed from immutable recordset releases
-- -----------------------------------------------------------------------------

INSERT INTO public.dataset_release (
    dataset_release_id,
    dataset_id,
    release_number,
    release_date,
    release_notes,
    release_status,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    -- Live: IDC/WordPress have published it, so any further change to this
    -- dataset needs a new version number rather than an in-place overwrite.
    (1, 1, 1, NOW(), 'Initial Release', 'live', NOW(), 0, NOW(), 0),
    (2, 2, 1, NOW(), 'Initial Release', 'released', NOW(), 0, NOW(), 0),
    -- Draft: still being assembled, so release_date is null (set only when
    -- release_status transitions to released). Recordset release 8 is frozen
    -- and ready to be added to it, so this dataset reads as "assembling v1".
    (3, 3, 1, NULL, 'Assembling first release', 'draft', NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.dataset_release', 'dataset_release_id'), COALESCE(MAX(dataset_release_id), 0), true) FROM public.dataset_release;

-- Recordset release 7 (recordset 3 v2) is intentionally absent: it is frozen
-- but not yet bundled, which is what makes "cut a new dataset release" the
-- next action for dataset 1. Dataset 3 has no dataset_release row at all.
INSERT INTO public.dataset_release_recordset (dataset_release_id, recordset_release_id) VALUES
    (1, 1),
    (1, 2),
    (1, 3),
    (1, 4),
    (2, 5),
    (2, 6);

-- -----------------------------------------------------------------------------
-- Dataset release transfers and destination-specific publication state
-- -----------------------------------------------------------------------------

INSERT INTO public.dataset_release_transfer (
    dataset_release_transfer_id,
    dataset_release_id,
    destination_id,
    transfer_name,
    transfer_mode_id,
    transfer_status,
    transfer_notes,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    -- Statuses are spread across the transfer_status vocabulary
    -- (draft | queued | in_progress | success | failed) so destination chips,
    -- status badges, and the "transfer failed" blocked state all have data.
    (1, 1, 1, 'RIDER-LUNG-CT IDC grouped release', 2, 'queued', 'Initial grouped IDC test transfer', NOW(), 0, NOW(), 0),
    (2, 1, 3, 'RIDER-LUNG-CT WordPress release', 1, 'success', 'Initial WordPress test transfer', NOW(), 0, NOW(), 0),
    (3, 2, 1, 'RIDER-LUNGCT-SEG IDC grouped release', 2, 'draft', 'Initial IDC test transfer for analysis result', NOW(), 0, NOW(), 0),
    (4, 1, 5, 'RIDER-LUNG-CT NBIA release', 1, 'failed', 'Initial NBIA test transfer', NOW(), 0, NOW(), 0),
    (5, 1, 2, 'RIDER-LUNG-CT General Commons limited release', 1, 'in_progress', 'Initial General Commons test transfer', NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.dataset_release_transfer', 'dataset_release_transfer_id'), COALESCE(MAX(dataset_release_transfer_id), 0), true) FROM public.dataset_release_transfer;

-- Transfer recordset membership. Manifest file IDs are left null so this script does
-- not require extra test manifest files in public.file.
INSERT INTO public.transfer_recordset (dataset_release_transfer_id, recordset_release_id, retriever_manifest_file_id) VALUES
    (1, 1, null),
    (1, 2, null),
    (1, 4, null),
    (2, 4, null),
    (3, 5, null),
    (4, 1, null),
    (4, 2, null),
    (5, 3, null);

INSERT INTO public.transfer_idc (
    dataset_release_transfer_id,
    base_gcs_url,
    dataset_manifest_file_id,
    imaging_manifest_file_id,
    clinical_manifest_file_id,
    published,
    "public"
) VALUES
    (1, 'gs://idc-test-bucket/rider-lung-ct/v1', null, null, null, false, false),
    (3, 'gs://idc-test-bucket/rider-lungct-seg/v1', null, null, null, false, false);

INSERT INTO public.transfer_wp (
    dataset_release_transfer_id,
    wp_media_file_id,
    published,
    "public"
) VALUES
    (2, null, false, false);

INSERT INTO public.transfer_nbia (
    dataset_release_transfer_id,
    collection,
    site,
    published,
    "public"
) VALUES
    (4, 'RIDER-LUNG-CT', 'TCIA', false, false);

INSERT INTO public.transfer_gc (
    dataset_release_transfer_id,
    published,
    "public"
) VALUES
    (5, false, false);

-- -----------------------------------------------------------------------------
-- WordPress object mapping examples
-- -----------------------------------------------------------------------------

INSERT INTO public.wp_object_map (
    map_id,
    posda_object_type,
    posda_object_id,
    wp_object_type,
    wp_object_id,
    wp_edit_url,
    wp_view_url,
    parent_wp_object_id,
    when_synced
) VALUES
    (1, 'dataset', 1, 'collection', 1001, 'https://wp.example.org/wp-admin/post.php?post=1001&action=edit', 'https://wp.example.org/collections/rider-lung-ct', null, NOW()),
    (2, 'dataset', 2, 'analysis_result', 1002, 'https://wp.example.org/wp-admin/post.php?post=1002&action=edit', 'https://wp.example.org/analysis-results/rider-lungct-seg', 1001, NOW()),
    (3, 'recordset', 1, 'download', 2001, 'https://wp.example.org/wp-admin/post.php?post=2001&action=edit', 'https://wp.example.org/downloads/radiology-01-public', 1001, NOW()),
    (4, 'recordset', 4, 'download', 2004, 'https://wp.example.org/wp-admin/post.php?post=2004&action=edit', 'https://wp.example.org/downloads/clinical-01-public', 1001, NOW()),
    (5, 'dataset_release', 1, 'version', 3001, 'https://wp.example.org/wp-admin/post.php?post=3001&action=edit', 'https://wp.example.org/collections/rider-lung-ct/v1', 1001, NOW());
SELECT setval(pg_get_serial_sequence('public.wp_object_map', 'map_id'), COALESCE(MAX(map_id), 0), true) FROM public.wp_object_map;

-- -----------------------------------------------------------------------------
-- QC reviews, assignments, and series
--
-- Covers every review_status the UI branches on (open / stale / complete /
-- cancelled), both review_types (full / partial), and both assignment states
-- that matter for intake (claimed vs unclaimed-in-the-pickup-queue).
--
-- SERIES UIDs: each qc_review gets one row derived from the draft's real
-- file_series (correct series_file_hash, so stale detection and the
-- per-series file lookup both resolve), plus synthetic rows so counts and the
-- per-modality progress table have enough volume to be legible. The fixture
-- files only contain a single CT series per draft, which is too thin to
-- exercise progress percentages or a modality breakdown.
-- Synthetic UIDs use the ...TEST.<review><nn> pattern; per-series file lookups
-- (Mirabelle's endpoint) will return nothing for those.
--
-- assigned_to is 0 (system user) so the script stays portable. To populate
-- "My QC Queue" on the dashboard, point one at yourself:
--   UPDATE public.qc_review_assignment SET assigned_to = <your user_id>
--    WHERE assignment_id = 1;
-- -----------------------------------------------------------------------------

INSERT INTO public.qc_review (
    qc_review_id,
    recordset_draft_id,
    review_status,
    review_notes,
    cloned_from_review_id,
    review_type,
    sample_percentage,
    sample_seed,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    (1, 1, 'open',      'Full review, in progress',                    null, 'full',    null, null, NOW(), 0, NOW(), 0),
    (2, 2, 'stale',     'Draft changed after sampling - needs re-clone', null, 'full',   null, null, NOW(), 0, NOW(), 0),
    (3, 4, 'complete',  'All series approved - draft is publishable',   null, 'full',    null, null, NOW(), 0, NOW(), 0),
    (4, 5, 'open',      'Partial sampled review, awaiting pickup',      null, 'partial', 25.0, 42,   NOW(), 0, NOW(), 0),
    (5, 6, 'cancelled', 'Abandoned - should be ignored by rollups',     null, 'full',    null, null, NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.qc_review', 'qc_review_id'), COALESCE(MAX(qc_review_id), 0), true) FROM public.qc_review;

-- One slice per review (the auto-created whole-review assignment). Review 4's
-- slice is unclaimed, which is what puts it on the /qc/queue pickup page.
INSERT INTO public.qc_review_assignment (
    assignment_id,
    qc_review_id,
    assigned_to,
    assignment_status,
    share_percentage,
    when_created,
    who_created,
    when_updated,
    who_updated
) VALUES
    (1, 1, 0,    'in_progress', 100, NOW(), 0, NOW(), 0),
    (2, 2, 0,    'in_progress', 100, NOW(), 0, NOW(), 0),
    (3, 3, 0,    'complete',    100, NOW(), 0, NOW(), 0),
    (4, 4, null, 'needs_qc',    100, NOW(), 0, NOW(), 0),
    (5, 5, null, 'needs_qc',    100, NOW(), 0, NOW(), 0);
SELECT setval(pg_get_serial_sequence('public.qc_review_assignment', 'assignment_id'), COALESCE(MAX(assignment_id), 0), true) FROM public.qc_review_assignment;

-- Real series, one per draft, with the content hash the sampler would compute.
INSERT INTO public.qc_unit (qc_review_id, assignment_id, unit_type, series_instance_uid, modality, unit_hash, qc_status, notes)
SELECT
    r.qc_review_id,
    a.assignment_id,
    'series',
    fs.series_instance_uid,
    max(fs.modality),
    md5(string_agg(f.digest, '' ORDER BY f.digest)),
    r.seed_status,
    null
FROM (VALUES
        (1, 1, 'approved'),
        (2, 2, 'pending'),
        (3, 4, 'approved'),
        (4, 5, 'pending'),
        (5, 6, 'pending')
     ) AS r(qc_review_id, recordset_draft_id, seed_status)
JOIN public.qc_review_assignment a ON a.qc_review_id = r.qc_review_id
JOIN public.recordset_draft_file rdf ON rdf.recordset_draft_id = r.recordset_draft_id
JOIN public.file_series fs ON fs.file_id = rdf.file_id
JOIN public.file f ON f.file_id = rdf.file_id
GROUP BY r.qc_review_id, a.assignment_id, fs.series_instance_uid, r.seed_status;

-- Synthetic series for volume. Review 1 spans three modalities and every
-- qc_status so the modality progress table and status chips are exercised.
INSERT INTO public.qc_unit (qc_review_id, assignment_id, unit_type, series_instance_uid, modality, unit_hash, qc_status, notes) VALUES
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0102', 'CT', md5('synthetic-0102'), 'approved', null),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0103', 'CT', md5('synthetic-0103'), 'approved', null),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0104', 'CT', md5('synthetic-0104'), 'pending',  null),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0105', 'CT', md5('synthetic-0105'), 'pending',  null),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0106', 'MR', md5('synthetic-0106'), 'approved', null),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0107', 'MR', md5('synthetic-0107'), 'rejected', 'Motion artifact through the volume'),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0108', 'MR', md5('synthetic-0108'), 'pending',  null),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0109', 'PT', md5('synthetic-0109'), 'flagged',  'Possible PHI burned into overlay'),
    (1, 1, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0110', 'PT', md5('synthetic-0110'), 'approved', null),
    -- Review 2 (stale): hashes deliberately will not match a recompute.
    (2, 2, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0201', 'CT', md5('stale-0201'), 'approved', null),
    (2, 2, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0202', 'CT', md5('stale-0202'), 'pending',  null),
    (2, 2, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0203', 'MR', md5('stale-0203'), 'approved', null),
    -- Review 3 (complete): every series approved, which is what unblocks publish.
    (3, 3, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0301', 'CT', md5('complete-0301'), 'approved', null),
    (3, 3, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0302', 'CT', md5('complete-0302'), 'approved', null),
    -- Review 4 (partial, unclaimed): all pending, nobody has started.
    (4, 4, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0401', 'CT', md5('partial-0401'), 'pending', null),
    (4, 4, 'series', '1.3.6.1.4.1.14519.5.2.1.TEST.0402', 'MR', md5('partial-0402'), 'pending', null);
SELECT setval(pg_get_serial_sequence('public.qc_unit', 'qc_unit_id'), COALESCE(MAX(qc_unit_id), 0), true) FROM public.qc_unit;

-- Audit trail for a few of review 1's decisions (resolve the surrogate qc_unit_id
-- from the natural (review, series) key).
INSERT INTO public.qc_unit_history (qc_unit_id, previous_status, new_status, when_updated, who_updated, notes)
SELECT u.qc_unit_id, v.previous_status, v.new_status, NOW(), 0, v.notes
FROM (VALUES
    (1, '1.3.6.1.4.1.14519.5.2.1.TEST.0102', 'pending',  'approved', null),
    (1, '1.3.6.1.4.1.14519.5.2.1.TEST.0103', 'pending',  'approved', null),
    (1, '1.3.6.1.4.1.14519.5.2.1.TEST.0107', 'pending',  'rejected', 'Motion artifact through the volume'),
    (1, '1.3.6.1.4.1.14519.5.2.1.TEST.0109', 'pending',  'flagged',  'Possible PHI burned into overlay'),
    (1, '1.3.6.1.4.1.14519.5.2.1.TEST.0109', 'flagged',  'flagged',  'Second look scheduled')
) AS v(qc_review_id, series_instance_uid, previous_status, new_status, notes)
JOIN public.qc_unit u
  ON u.qc_review_id = v.qc_review_id AND u.series_instance_uid = v.series_instance_uid;
SELECT setval(pg_get_serial_sequence('public.qc_unit_history', 'history_id'), COALESCE(MAX(history_id), 0), true) FROM public.qc_unit_history;

COMMIT;
