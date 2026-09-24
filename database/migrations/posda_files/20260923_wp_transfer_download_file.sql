-- Reshape transfer_recordset for the WordPress transfer.
--
-- A WordPress transfer uploads each recordset release's data file to the WP
-- media library and points that recordset's download page at it -- the same
-- flow manifest/attach already runs for the retriever manifest. Both end as the
-- download page's download_file, so they share one column, renamed from
-- retriever_manifest_file_id to name the field it populates rather than the
-- kind of file in it.
--
-- A row can only ever hold one kind: transfer_recordset is keyed per transfer,
-- and a transfer has exactly one destination.
--
-- transfer_wp is dropped. wp_media_file_id could never have worked (one row per
-- transfer, but each recordset release needs its own attachment), and
-- published / public were never populated or read.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

ALTER TABLE "public".transfer_recordset
    RENAME COLUMN retriever_manifest_file_id TO download_file_id;

ALTER TABLE "public".transfer_recordset
    RENAME CONSTRAINT fk_transfer_dataset_retriever_manifest_file
    TO fk_transfer_recordset_download_file;

COMMENT ON COLUMN "public".transfer_recordset.download_file_id IS
    'the file that becomes this recordset''s WP download page download_file -- '
    'the generated retriever manifest for idc/nbia/gc, the recordset '
    'release''s own data file for wp. Destination is the discriminator; nothing '
    'enforces it.';

DROP TABLE "public".transfer_wp CASCADE;
