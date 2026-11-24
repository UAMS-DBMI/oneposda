-- The Croissant JSON-LD generated for a dataset release at Disseminate.
--
-- Stored as a Posda file like the retriever manifests, so ensure_wp_media
-- dedups the upload to the WordPress media library, and Disseminate can tell
-- whether the collection page's croissant_manifest holds this exact file.
-- Null until generated; go-live refuses while it is null or stale.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

ALTER TABLE "public".dataset_release
    ADD COLUMN croissant_file_id integer;

ALTER TABLE "public".dataset_release
    ADD CONSTRAINT fk_dataset_release_croissant_file
    FOREIGN KEY ( croissant_file_id ) REFERENCES "public"."file"( file_id )
    ON DELETE RESTRICT;
