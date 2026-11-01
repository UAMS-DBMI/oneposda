-- Make a non-DICOM QC file unit a snapshot of what was reviewed, like a series
-- unit, instead of a pointer to a draft membership row.
--
-- A series unit records its identity (series_instance_uid) and content
-- (unit_hash) and has no link to the draft. A file unit instead referenced
-- recordset_draft_file_id with ON DELETE CASCADE, so removing or replacing a
-- file in the draft deleted the unit and its decision history -- a rejection
-- and its reason vanished, and the stale review was left empty.
--
-- File units now carry file_id (content) and file_name (identity) themselves.
-- "Still in the draft?" is a join on (draft, file_id, file_name), as series
-- membership already is, and only deleting the review removes a unit.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

ALTER TABLE "public".qc_unit
    ADD COLUMN file_id integer,
    ADD COLUMN file_name text;

UPDATE "public".qc_unit u
SET file_id = rdf.file_id,
    file_name = rdf.file_name
FROM "public".recordset_draft_file rdf
WHERE rdf.recordset_draft_file_id = u.recordset_draft_file_id;

ALTER TABLE "public".qc_unit
    DROP CONSTRAINT ck_qc_unit_type,
    DROP CONSTRAINT unq_qc_unit_file,
    DROP CONSTRAINT fk_qc_unit_recordset_draft_file,
    DROP COLUMN recordset_draft_file_id;

ALTER TABLE "public".qc_unit
    ADD CONSTRAINT fk_qc_unit_file
        FOREIGN KEY (file_id) REFERENCES "public".file (file_id),
    ADD CONSTRAINT ck_qc_unit_type CHECK (
        (unit_type = 'series' AND series_instance_uid IS NOT NULL
             AND file_id IS NULL AND file_name IS NULL)
        OR (unit_type = 'file' AND file_id IS NOT NULL
             AND series_instance_uid IS NULL)
    ),
    -- Mirrors the draft's own (draft, file_id, file_name) membership key.
    ADD CONSTRAINT unq_qc_unit_file UNIQUE (qc_review_id, file_id, file_name);

COMMENT ON COLUMN "public".qc_unit.file_id IS
    'File unit: the content reviewed (file is content-addressed). Null for series.';
COMMENT ON COLUMN "public".qc_unit.file_name IS
    'File unit: the name the file had in the draft -- its identity across versions.';
