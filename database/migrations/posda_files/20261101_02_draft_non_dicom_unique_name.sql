-- A draft may not hold two different non-DICOM files under one name.
--
-- A non-DICOM file's name is its identity in the recordset (a corrected
-- uid_crosswalk.csv replaces the old one; it doesn't sit beside it). Adding a
-- same-named file is resolved by the caller -- replace the draft's file or skip
-- the incoming one -- and this trigger is the backstop for any path that
-- doesn't. Content-identical files under *different* names stay allowed, and
-- DICOM is exempt (activity DICOM carries no name at all).
--
-- A trigger rather than a partial unique index: "is it DICOM" lives on file,
-- and an index predicate can't reach another table. An unprocessed file
-- (is_dicom_file null) counts as non-DICOM, as everywhere else in the module.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

CREATE OR REPLACE FUNCTION "public".recordset_draft_file_unique_non_dicom_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.file_name IS NULL THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        SELECT 1 FROM "public".file f
        WHERE f.file_id = NEW.file_id AND f.is_dicom_file = true
    ) THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        SELECT 1
        FROM "public".recordset_draft_file rdf
        JOIN "public".file f ON f.file_id = rdf.file_id
        WHERE rdf.recordset_draft_id = NEW.recordset_draft_id
          AND rdf.file_name = NEW.file_name
          AND rdf.file_id <> NEW.file_id
          AND rdf.recordset_draft_file_id IS DISTINCT FROM NEW.recordset_draft_file_id
          AND coalesce(f.is_dicom_file, false) = false
    ) THEN
        RAISE EXCEPTION 'draft % already has a different non-DICOM file named "%"',
            NEW.recordset_draft_id, NEW.file_name
            USING ERRCODE = 'unique_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_recordset_draft_file_unique_non_dicom_name
    BEFORE INSERT OR UPDATE OF file_id, file_name, recordset_draft_id
    ON "public".recordset_draft_file
    FOR EACH ROW
    EXECUTE FUNCTION "public".recordset_draft_file_unique_non_dicom_name();
