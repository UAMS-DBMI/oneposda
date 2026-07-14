DROP TABLE IF EXISTS "public".collection_release_dataset;
DROP TABLE IF EXISTS "public".transfer_wp;
DROP TABLE IF EXISTS "public".transfer_idc;
DROP TABLE IF EXISTS "public".transfer_gc;
DROP TABLE IF EXISTS "public".transfer_dataset;
DROP TABLE IF EXISTS "public".transfer_aspera;
DROP TABLE IF EXISTS "public".dataset_release_file;
DROP TABLE IF EXISTS "public".dataset_release_draft_file;
DROP TABLE IF EXISTS "public".dataset_release_draft;
DROP TABLE IF EXISTS "public".dataset_release;
DROP TABLE IF EXISTS "public".dataset_destination;
DROP TABLE IF EXISTS "public".dataset;
DROP TABLE IF EXISTS "public".collection_release_transfer;
DROP TABLE IF EXISTS "public".wp_object_map;
DROP TABLE IF EXISTS "public".transfer_destination;
DROP TABLE IF EXISTS "public".dataset_license;
DROP TABLE IF EXISTS "public".collection_release;
DROP TABLE IF EXISTS "public".collection_related;
DROP TABLE IF EXISTS "public".collection;


CREATE  TABLE "public".collection ( 
	collection_id        integer  NOT NULL  ,
	collection_doi       text    ,
	collection_type      integer    ,
	collection_short_title text    ,
	collection_title     text    ,
	collection_name      text    ,
	active               boolean    ,
	when_created         timestamptz    ,
	who_updated          text    ,
	when_updated         timestamptz    ,
	who_created          text    ,
	CONSTRAINT pk_collection PRIMARY KEY ( collection_id ),
	CONSTRAINT unq_collection_doi UNIQUE ( collection_doi ) 
 ) ;

CREATE  TABLE "public".collection_related ( 
	collection_id        integer  NOT NULL  ,
	related_collection_id integer  NOT NULL  ,
	relation_type        text    ,
	CONSTRAINT pk_related_collection PRIMARY KEY ( collection_id, related_collection_id )
 ) ;

ALTER TABLE "public".collection_related ADD CONSTRAINT fk_related_collection_collection FOREIGN KEY ( collection_id ) REFERENCES "public".collection( collection_id )   ;

ALTER TABLE "public".collection_related ADD CONSTRAINT fk_related_collection_related_collection FOREIGN KEY ( related_collection_id ) REFERENCES "public".collection( collection_id )   ;

CREATE  TABLE "public".collection_release ( 
	collection_release_id integer  NOT NULL  ,
	collection_id        integer  NOT NULL  ,
	release_number       integer    ,
	release_date         timestamptz    ,
	release_notes        text    ,
	when_created         timestamptz    ,
	who_created          text    ,
	when_updated         timestamptz    ,
	who_updated          text    ,
	CONSTRAINT pk_collection_release PRIMARY KEY ( collection_release_id )
 ) ;

CREATE UNIQUE INDEX unq_collection_release_collection_release_num ON "public".collection_release ( collection_id, release_number ) ;

CREATE INDEX idx_collection_release_collection_id ON "public".collection_release  ( collection_id ) ;

ALTER TABLE "public".collection_release ADD CONSTRAINT fk_collection_release_collection FOREIGN KEY ( collection_id ) REFERENCES "public".collection( collection_id )   ;

CREATE  TABLE "public".dataset_license ( 
	license_id           integer  NOT NULL  ,
	license_label        text    ,
	license_url          text    ,
	CONSTRAINT pk_dataset_license PRIMARY KEY ( license_id )
 ) ;

CREATE  TABLE "public".transfer_destination ( 
	destination_id       integer  NOT NULL  ,
	name                 text    ,
	CONSTRAINT pk_destination PRIMARY KEY ( destination_id )
 ) ;

CREATE  TABLE "public".wp_object_map ( 
	map_id               integer  NOT NULL  ,
	posda_object_type    text    ,
	posda_object_id      integer    ,
	wp_object_type       text    ,
	wp_object_id         integer    ,
	wp_edit_url          text    ,
	wp_view_url          text    ,
	parent_wp_object_id  integer    ,
	when_synced          timestamptz    ,
	CONSTRAINT pk_wp_object_map PRIMARY KEY ( map_id ),
	CONSTRAINT unq_wp_object_map_posda_object UNIQUE ( posda_object_type, posda_object_id ) ,
	CONSTRAINT idx_wp_object_map_wp_object UNIQUE ( wp_object_type, wp_object_id ) 
 ) ;

COMMENT ON COLUMN "public".wp_object_map.posda_object_type IS 'collection, dataset, collection_release, dataset_release';

COMMENT ON COLUMN "public".wp_object_map.wp_object_type IS 'collection, analysis_result, download, version, version_download';

CREATE  TABLE "public".collection_release_transfer ( 
	collection_release_transfer_id integer  NOT NULL  ,
	collection_release_id integer  NOT NULL  ,
	destination_id       integer  NOT NULL  ,
	transfer_name        text    ,
	transfer_mode        text    ,
	transfer_status      text    ,
	transfer_notes       text    ,
	when_created         timestamptz    ,
	who_created          text    ,
	when_updated         timestamptz    ,
	who_updated          text    ,
	CONSTRAINT pk_collection_release_transfer PRIMARY KEY ( collection_release_transfer_id )
 ) ;

CREATE INDEX idx_collection_release_transfer_collection_release_id ON "public".collection_release_transfer  ( collection_release_id ) ;

COMMENT ON COLUMN "public".collection_release_transfer.transfer_mode IS 'optional, such as single_dataset, grouped_dicom, clinical_bundle';

COMMENT ON COLUMN "public".collection_release_transfer.transfer_status IS 'draft, queued, submitted, failed';

ALTER TABLE "public".collection_release_transfer ADD CONSTRAINT fk_collection_release_transfer_destination FOREIGN KEY ( destination_id ) REFERENCES "public".transfer_destination( destination_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".collection_release_transfer ADD CONSTRAINT fk_collection_release_transfer_collection_release FOREIGN KEY ( collection_release_id ) REFERENCES "public".collection_release( collection_release_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".dataset ( 
	dataset_id           integer  NOT NULL  ,
	dataset_doi          text    ,
	collection_id        integer  NOT NULL  ,
	license_id           integer  NOT NULL  ,
	dataset_type         text    ,
	dataset_title        text    ,
	active               boolean    ,
	when_created         timestamptz    ,
	who_created          text    ,
	when_updated         timestamptz    ,
	who_updated          text    ,
	CONSTRAINT pk_dataset PRIMARY KEY ( dataset_id ),
	CONSTRAINT unq_dataset_doi UNIQUE ( dataset_doi ) 
 ) ;

ALTER TABLE "public".dataset ADD CONSTRAINT fk_dataset_collection FOREIGN KEY ( collection_id ) REFERENCES "public".collection( collection_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".dataset ADD CONSTRAINT fk_dataset_dataset_license FOREIGN KEY ( license_id ) REFERENCES "public".dataset_license( license_id )   ;

CREATE  TABLE "public".dataset_destination ( 
	dataset_id           integer  NOT NULL  ,
	destination_id       integer  NOT NULL  ,
	default_display      boolean  NOT NULL  ,
	default_transfer_mode text    ,
	CONSTRAINT pk_dataset_destination PRIMARY KEY ( dataset_id, destination_id )
 ) ;

CREATE UNIQUE INDEX unq_dataset_destination_one_default_display ON "public".dataset_destination ( dataset_id ) WHERE default_display = true;

ALTER TABLE "public".dataset_destination ADD CONSTRAINT fk_dataset_destination_destination FOREIGN KEY ( destination_id ) REFERENCES "public".transfer_destination( destination_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".dataset_destination ADD CONSTRAINT fk_dataset_destination_dataset FOREIGN KEY ( dataset_id ) REFERENCES "public".dataset( dataset_id ) ON DELETE CASCADE  ;

CREATE  TABLE "public".dataset_release ( 
	dataset_release_id   integer  NOT NULL  ,
	dataset_id           integer  NOT NULL  ,
	release_number       integer  NOT NULL  ,
	release_date         timestamptz  NOT NULL  ,
	release_notes        text    ,
	when_created         timestamptz    ,
	who_created          text    ,
	when_updated         timestamptz    ,
	who_updated          text    ,
	CONSTRAINT pk_dataset_release PRIMARY KEY ( dataset_release_id )
 ) ;

CREATE UNIQUE INDEX unq_dataset_release_dataset_release_num ON "public".dataset_release ( dataset_id, release_number ) ;

CREATE INDEX idx_dataset_release_dataset_id ON "public".dataset_release  ( dataset_id ) ;

ALTER TABLE "public".dataset_release ADD CONSTRAINT fk_dataset_release_dataset FOREIGN KEY ( dataset_id ) REFERENCES "public".dataset( dataset_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".dataset_release_draft ( 
	dataset_release_draft_id integer  NOT NULL  ,
	dataset_id           integer  NOT NULL  ,
	cloned_from_release_id integer    ,
	draft_name           text    ,
	draft_status         text    ,
	draft_notes          text    ,
	when_created         timestamptz    ,
	who_created          text    ,
	when_updated         timestamptz    ,
	who_updated          text    ,
	CONSTRAINT pk_dataset_release_draft PRIMARY KEY ( dataset_release_draft_id )
 ) ;

CREATE INDEX idx_dataset_release_draft_dataset_id ON "public".dataset_release_draft  ( dataset_id ) ;

CREATE INDEX idx_dataset_release_draft_dataset_when_created ON "public".dataset_release_draft  ( dataset_id, when_created  DESC   ) ;

ALTER TABLE "public".dataset_release_draft ADD CONSTRAINT fk_dataset_release_draft_dataset FOREIGN KEY ( dataset_id ) REFERENCES "public".dataset( dataset_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".dataset_release_draft ADD CONSTRAINT fk_dataset_release_draft_dataset_release FOREIGN KEY ( cloned_from_release_id ) REFERENCES "public".dataset_release( dataset_release_id )   ;

CREATE  TABLE "public".dataset_release_draft_file ( 
	dataset_release_draft_id integer  NOT NULL  ,
	file_id              integer  NOT NULL  ,
	CONSTRAINT pk_dataset_release_draft_file PRIMARY KEY ( dataset_release_draft_id, file_id )
 ) ;

CREATE INDEX idx_dataset_release_draft_file_file_id ON "public".dataset_release_draft_file  ( file_id ) ;

ALTER TABLE "public".dataset_release_draft_file ADD CONSTRAINT fk_dataset_release_draft_file_dataset_release_draft FOREIGN KEY ( dataset_release_draft_id ) REFERENCES "public".dataset_release_draft( dataset_release_draft_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".dataset_release_draft_file ADD CONSTRAINT fk_dataset_release_draft_file_file FOREIGN KEY ( file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".dataset_release_file ( 
	dataset_release_id   integer  NOT NULL  ,
	file_id              integer  NOT NULL  ,
	CONSTRAINT pk_dataset_release_file PRIMARY KEY ( dataset_release_id, file_id )
 ) ;

CREATE INDEX idx_dataset_release_file_file_id ON "public".dataset_release_file  ( file_id ) ;

ALTER TABLE "public".dataset_release_file ADD CONSTRAINT fk_dataset_release_file_dataset_release FOREIGN KEY ( dataset_release_id ) REFERENCES "public".dataset_release( dataset_release_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".dataset_release_file ADD CONSTRAINT fk_dataset_release_file_file FOREIGN KEY ( file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".transfer_aspera ( 
	collection_release_transfer_id integer  NOT NULL  ,
	published            boolean    ,
	"public"             boolean    ,
	faspex_url           text    ,
	CONSTRAINT pk_release_aspera PRIMARY KEY ( collection_release_transfer_id )
 ) ;

ALTER TABLE "public".transfer_aspera ADD CONSTRAINT fk_transfer_aspera_collection_release_transfer FOREIGN KEY ( collection_release_transfer_id ) REFERENCES "public".collection_release_transfer( collection_release_transfer_id ) ON DELETE CASCADE  ;

CREATE  TABLE "public".transfer_dataset ( 
	collection_release_transfer_id integer  NOT NULL  ,
	dataset_release_id   integer  NOT NULL  ,
	retriever_manifest_file_id integer    ,
	CONSTRAINT pk_collection_release_transfer_dataset_release PRIMARY KEY ( collection_release_transfer_id, dataset_release_id )
 ) ;

CREATE INDEX idx_transfer_dataset_dataset_release_id ON "public".transfer_dataset  ( dataset_release_id ) ;

ALTER TABLE "public".transfer_dataset ADD CONSTRAINT fk_collection_release_transfer_dataset_release_collection_release_transfer FOREIGN KEY ( collection_release_transfer_id ) REFERENCES "public".collection_release_transfer( collection_release_transfer_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".transfer_dataset ADD CONSTRAINT fk_collection_release_transfer_dataset_release_dataset_release FOREIGN KEY ( dataset_release_id ) REFERENCES "public".dataset_release( dataset_release_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".transfer_dataset ADD CONSTRAINT fk_collection_release_transfer_dataset_release_file FOREIGN KEY ( retriever_manifest_file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".transfer_gc ( 
	collection_release_transfer_id integer  NOT NULL  ,
	published            boolean    ,
	"public"             boolean    ,
	CONSTRAINT pk_release_gc PRIMARY KEY ( collection_release_transfer_id )
 ) ;

ALTER TABLE "public".transfer_gc ADD CONSTRAINT fk_transfer_gc_collection_release_transfer FOREIGN KEY ( collection_release_transfer_id ) REFERENCES "public".collection_release_transfer( collection_release_transfer_id ) ON DELETE CASCADE  ;

CREATE  TABLE "public".transfer_idc ( 
	collection_release_transfer_id integer  NOT NULL  ,
	gcs_url              text    ,
	dataset_manifest_file_id integer    ,
	collection_manifest_file_id integer    ,
	clinical_manifest_file_id integer    ,
	published            boolean    ,
	"public"             boolean    ,
	CONSTRAINT pk_release_idc PRIMARY KEY ( collection_release_transfer_id )
 ) ;

ALTER TABLE "public".transfer_idc ADD CONSTRAINT fk_release_idc_file_dataset_manifest FOREIGN KEY ( dataset_manifest_file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".transfer_idc ADD CONSTRAINT fk_release_idc_file_collection_manifest FOREIGN KEY ( collection_manifest_file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".transfer_idc ADD CONSTRAINT fk_release_idc_file_download_manifest FOREIGN KEY ( clinical_manifest_file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".transfer_idc ADD CONSTRAINT fk_transfer_idc_collection_release_transfer FOREIGN KEY ( collection_release_transfer_id ) REFERENCES "public".collection_release_transfer( collection_release_transfer_id ) ON DELETE CASCADE  ;

CREATE  TABLE "public".transfer_wp ( 
	collection_release_transfer_id integer  NOT NULL  ,
	wp_media_file_id     integer    ,
	published            boolean    ,
	"public"             boolean    ,
	CONSTRAINT pk_release_wp PRIMARY KEY ( collection_release_transfer_id )
 ) ;

ALTER TABLE "public".transfer_wp ADD CONSTRAINT fk_transfer_wp_collection_release_transfer FOREIGN KEY ( collection_release_transfer_id ) REFERENCES "public".collection_release_transfer( collection_release_transfer_id ) ON DELETE CASCADE  ;

CREATE  TABLE "public".collection_release_dataset ( 
	collection_release_id integer  NOT NULL  ,
	dataset_release_id   integer  NOT NULL  ,
	CONSTRAINT pk_collection_release_dataset PRIMARY KEY ( collection_release_id, dataset_release_id )
 ) ;

CREATE INDEX idx_collection_release_dataset_dataset_release_id ON "public".collection_release_dataset  ( dataset_release_id ) ;

ALTER TABLE "public".collection_release_dataset ADD CONSTRAINT fk_collection_release_dataset_collection_release FOREIGN KEY ( collection_release_id ) REFERENCES "public".collection_release( collection_release_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".dataset_release_recordset ADD CONSTRAINT fk_dataset_release_recordset_recordset_release FOREIGN KEY ( recordset_release_id ) REFERENCES "public".recordset_release( recordset_release_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".recordset_draft ( 
	recordset_draft_id   integer  NOT NULL GENERATED BY DEFAULT AS IDENTITY ,
	recordset_id         integer  NOT NULL  ,
	draft_name           text  NOT NULL  ,
	draft_status         text  NOT NULL  ,
	draft_notes          text    ,
	cloned_from_release_id integer    ,
	when_created         timestamptz    ,
	who_created          integer    ,
	when_updated         timestamptz    ,
	who_updated          integer    ,
	CONSTRAINT pk_recordset_draft PRIMARY KEY ( recordset_draft_id )
 ) ;

CREATE INDEX idx_recordset_draft_recordset_id ON "public".recordset_draft  ( recordset_id ) ;

COMMENT ON COLUMN "public".recordset_draft.draft_status IS 'open, ready, invalid, published, deleted';

ALTER TABLE "public".recordset_draft ADD CONSTRAINT fk_recordset_draft_recordset FOREIGN KEY ( recordset_id ) REFERENCES "public".recordset( recordset_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".recordset_draft ADD CONSTRAINT fk_recordset_draft_recordset_release FOREIGN KEY ( cloned_from_release_id ) REFERENCES "public".recordset_release( recordset_release_id )   ;

ALTER TABLE "public".recordset_draft ADD CONSTRAINT fk_recordset_draft_who_created FOREIGN KEY ( who_created ) REFERENCES auth.users( user_id )   ;

ALTER TABLE "public".recordset_draft ADD CONSTRAINT fk_recordset_draft_who_updated FOREIGN KEY ( who_updated ) REFERENCES auth.users( user_id )   ;

CREATE  TABLE "public".recordset_draft_file ( 
	recordset_draft_id   integer  NOT NULL  ,
	file_id              integer  NOT NULL  ,
	CONSTRAINT pk_recordset_draft_file PRIMARY KEY ( recordset_draft_id, file_id )
 ) ;

CREATE INDEX idx_recordset_draft_file_file_id ON "public".recordset_draft_file  ( file_id ) ;

ALTER TABLE "public".recordset_draft_file ADD CONSTRAINT fk_recordset_draft_file_recordset_draft FOREIGN KEY ( recordset_draft_id ) REFERENCES "public".recordset_draft( recordset_draft_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".recordset_draft_file ADD CONSTRAINT fk_recordset_draft_file_file FOREIGN KEY ( file_id ) REFERENCES "public"."file"( file_id ) ON DELETE RESTRICT  ;

CREATE  TABLE "public".qc_review ( 
	qc_review_id         integer  NOT NULL GENERATED BY DEFAULT AS IDENTITY ,
	recordset_draft_id   integer  NOT NULL  ,
	review_status        text DEFAULT 'open'::text NOT NULL  ,
	review_notes         text    ,
	cloned_from_review_id integer    ,
	when_created         timestamptz    ,
	who_created          integer    ,
	when_updated         timestamptz    ,
	who_updated          integer    ,
	review_type          text DEFAULT 'full'::text NOT NULL  ,
	sample_percentage    decimal    ,
	sample_seed          integer    ,
	CONSTRAINT pk_qc_review PRIMARY KEY ( qc_review_id )
 ) ;

COMMENT ON COLUMN "public".qc_review.review_status IS 'open | complete | cancelled | stale';

COMMENT ON COLUMN "public".qc_review.review_type IS 'full | partial';

COMMENT ON COLUMN "public".qc_review.sample_percentage IS 'uniform % per modality when partial; NULL when full';

COMMENT ON COLUMN "public".qc_review.sample_seed IS 'optional; reproduces a draw / deterministic re-draw; qc_series rows are the membership source of truth';

ALTER TABLE "public".qc_review ADD CONSTRAINT fk_qc_review_cloned_from FOREIGN KEY ( cloned_from_review_id ) REFERENCES "public".qc_review( qc_review_id ) ON DELETE RESTRICT  ;

ALTER TABLE "public".qc_review ADD CONSTRAINT fk_qc_review_recordset_draft FOREIGN KEY ( recordset_draft_id ) REFERENCES "public".recordset_draft( recordset_draft_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".qc_review ADD CONSTRAINT fk_qc_review_who_created FOREIGN KEY ( who_created ) REFERENCES auth.users( user_id )   ;

ALTER TABLE "public".qc_review ADD CONSTRAINT fk_qc_review_who_updated FOREIGN KEY ( who_updated ) REFERENCES auth.users( user_id )   ;

CREATE  TABLE "public".qc_review_assignment ( 
	assignment_id        integer  NOT NULL GENERATED BY DEFAULT AS IDENTITY ,
	qc_review_id         integer  NOT NULL  ,
	assigned_to          integer    ,
	assignment_status    text DEFAULT 'needs_qc'::text NOT NULL  ,
	share_percentage     decimal    ,
	when_created         timestamptz    ,
	who_created          integer    ,
	when_updated         timestamptz    ,
	who_updated          integer    ,
	CONSTRAINT pk_qc_review_assignment PRIMARY KEY ( assignment_id )
 ) ;

CREATE INDEX idx_qc_review_assignment_qc_review_id ON "public".qc_review_assignment USING  btree ( qc_review_id ) ;

CREATE INDEX idx_qc_review_assignment_assigned_to ON "public".qc_review_assignment USING  btree ( assigned_to ) ;

COMMENT ON COLUMN "public".qc_review_assignment.assigned_to IS 'NULL = unclaimed (appears on the needs-QC pickup page)';

COMMENT ON COLUMN "public".qc_review_assignment.assignment_status IS 'needs_qc | in_progress | complete';

COMMENT ON COLUMN "public".qc_review_assignment.share_percentage IS 'even share of each modality for this slice; whole review = 100';

ALTER TABLE "public".qc_review_assignment ADD CONSTRAINT fk_qc_review_assignment_qc_review FOREIGN KEY ( qc_review_id ) REFERENCES "public".qc_review( qc_review_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".qc_review_assignment ADD CONSTRAINT fk_qc_review_assignment_assigned_to FOREIGN KEY ( assigned_to ) REFERENCES auth.users( user_id )   ;

ALTER TABLE "public".qc_review_assignment ADD CONSTRAINT fk_qc_review_assignment_who_created FOREIGN KEY ( who_created ) REFERENCES auth.users( user_id )   ;

ALTER TABLE "public".qc_review_assignment ADD CONSTRAINT fk_qc_review_assignment_who_updated FOREIGN KEY ( who_updated ) REFERENCES auth.users( user_id )   ;

CREATE  TABLE "public".qc_series ( 
	qc_review_id         integer  NOT NULL  ,
	series_instance_uid  text  NOT NULL  ,
	qc_status            text DEFAULT 'pending'::text NOT NULL  ,
	series_file_hash     text  NOT NULL  ,
	notes                text    ,
	modality             text    ,
	assignment_id        integer    ,
	CONSTRAINT pk_qc_series PRIMARY KEY ( qc_review_id, series_instance_uid )
 ) ;

CREATE INDEX idx_qc_series_assignment_id ON "public".qc_series  ( assignment_id ) ;

COMMENT ON COLUMN "public".qc_series.qc_status IS 'pending | approved | rejected | flagged';

COMMENT ON COLUMN "public".qc_series.modality IS 'denormalized snapshot from file_series, keyed by series_instance_uid';

ALTER TABLE "public".qc_series ADD CONSTRAINT fk_qc_series_qc_review FOREIGN KEY ( qc_review_id ) REFERENCES "public".qc_review( qc_review_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".qc_series ADD CONSTRAINT fk_qc_series_qc_review_assignment FOREIGN KEY ( assignment_id ) REFERENCES "public".qc_review_assignment( assignment_id ) ON DELETE SET NULL  ;

CREATE  TABLE "public".qc_series_history ( 
	history_id           integer  NOT NULL GENERATED BY DEFAULT AS IDENTITY ,
	qc_review_id         integer  NOT NULL  ,
	series_instance_uid  text  NOT NULL  ,
	previous_status      text    ,
	new_status           text  NOT NULL  ,
	when_updated         timestamptz DEFAULT now() NOT NULL  ,
	who_updated          integer    ,
	notes                text    ,
	CONSTRAINT pk_qc_series_history PRIMARY KEY ( history_id )
 ) ;

ALTER TABLE "public".qc_series_history ADD CONSTRAINT fk_qc_series_history_qc_review FOREIGN KEY ( qc_review_id ) REFERENCES "public".qc_review( qc_review_id ) ON DELETE CASCADE  ;

ALTER TABLE "public".qc_series_history ADD CONSTRAINT fk_qc_series_history_who_updated FOREIGN KEY ( who_updated ) REFERENCES auth.users( user_id )   ;

CREATE OR REPLACE FUNCTION public.notify_transfer_queued()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.transfer_status = 'queued' THEN
        PERFORM pg_notify('idc_transfer_channel', NEW.dataset_release_transfer_id::text);
    END IF;
    RETURN NEW;
END;
$function$;;

CREATE OR REPLACE FUNCTION public.qc_mark_open_reviews_stale()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  UPDATE public.qc_review q
     SET review_status = 'stale'
   WHERE q.review_status = 'open'
     AND q.recordset_draft_id IN (SELECT recordset_draft_id FROM changed);
  RETURN NULL;
END;
$function$;;

CREATE TRIGGER dataset_release_transfer_queued_notify AFTER INSERT OR UPDATE OF transfer_status ON public.dataset_release_transfer FOR EACH ROW EXECUTE FUNCTION notify_transfer_queued();

CREATE TRIGGER trg_recordset_draft_file_stale_del AFTER DELETE ON public.recordset_draft_file REFERENCING OLD TABLE AS changed FOR EACH STATEMENT EXECUTE FUNCTION qc_mark_open_reviews_stale();

CREATE TRIGGER trg_recordset_draft_file_stale_ins AFTER INSERT ON public.recordset_draft_file REFERENCING NEW TABLE AS changed FOR EACH STATEMENT EXECUTE FUNCTION qc_mark_open_reviews_stale();
