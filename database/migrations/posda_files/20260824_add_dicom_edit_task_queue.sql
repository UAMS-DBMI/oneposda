-- Distributed, restartable DICOM editing.
--
-- BackgroundEditorTp.pl held its entire work list in memory and drove it from a
-- single select() reactor, so killing the process lost the plan, stranded the
-- edits/<uuid> temp tree, and left dicom_edit_compare_disposition parked at
-- 'Comparisons In Progress' forever.
--
-- dicom_edit_task makes each file's progress durable. One row per SOP for the
-- whole life of an edit; `state` is a per-file state machine that workers
-- advance by claiming rows with FOR UPDATE SKIP LOCKED under a lease. A worker
-- that dies leaves its row in an *ing state with an expired lease_expires, and
-- the next claim reclaims it -- no reaper needed.
--
--   pending_edit -> editing -> pending_compare -> comparing -> compared
--                                                          -> unchanged
--                                             -> compare_failed
--                           -> edit_failed
--   compared -> pending_import -> importing -> imported   (after user accepts)
--                                           -> import_failed

CREATE TABLE public.dicom_edit_task (
    edit_task_id             bigserial PRIMARY KEY,
    subprocess_invocation_id integer     NOT NULL,
    sop_instance_uid         text        NOT NULL,
    from_file_id             integer     NOT NULL,
    from_path                text        NOT NULL,
    to_path                  text        NOT NULL,
    edit_spec                jsonb       NOT NULL,
    state                    text        NOT NULL DEFAULT 'pending_edit',
    attempts                 integer     NOT NULL DEFAULT 0,
    worker_id                text,
    lease_expires            timestamptz,
    from_file_digest         text,
    to_file_digest           text,
    to_file_id               integer,
    error                    text,
    updated_at               timestamptz NOT NULL DEFAULT now()
);

-- The planner streams rows in rather than accumulating them in a hash, so this
-- index -- not an in-memory %SopsToEdit lookup -- is what detects the same SOP
-- appearing in two series. It also makes re-running the planner idempotent.
CREATE UNIQUE INDEX dicom_edit_task_sop_uniq
    ON public.dicom_edit_task (subprocess_invocation_id, sop_instance_uid);

-- The claim path: ClaimEditTasks filters on (invocation, state) and orders by
-- edit_task_id, so this covers the index scan feeding FOR UPDATE SKIP LOCKED.
CREATE INDEX dicom_edit_task_claim
    ON public.dicom_edit_task (subprocess_invocation_id, state, edit_task_id);

-- Reclaiming expired leases scans by state and lease_expires across all edits.
CREATE INDEX dicom_edit_task_lease
    ON public.dicom_edit_task (state, lease_expires)
    WHERE lease_expires IS NOT NULL;

-- Import workers resolve to_file_id by digest; the timepoint build joins on
-- from_file_id.
CREATE INDEX dicom_edit_task_from_file
    ON public.dicom_edit_task (subprocess_invocation_id, from_file_id);

-- dicom_edit_compare had no uniqueness at all, so a retried compare (which was
-- impossible before, but is routine once a killed worker's task is reclaimed)
-- would insert a second row for the same file and double-count it in
-- DifferenceReportByEditId. Collapse any pre-existing duplicates first --
-- keeping the lowest ctid -- so the index can be created on live databases.
DELETE FROM public.dicom_edit_compare a
      USING public.dicom_edit_compare b
      WHERE a.ctid > b.ctid
        AND a.subprocess_invocation_id = b.subprocess_invocation_id
        AND a.from_file_digest = b.from_file_digest;

CREATE UNIQUE INDEX dicom_edit_compare_uniq
    ON public.dicom_edit_compare (subprocess_invocation_id, from_file_digest);

-- ImportEditsTp.pl creates one import_event for the whole accept, then the
-- files are imported by workers rather than by ImportEditsTp.pl itself. Park
-- the id on the run so every worker files its imports under the same event,
-- which is the provenance behaviour the single-process version had.
ALTER TABLE public.dicom_edit_compare_disposition
    ADD COLUMN import_event_id integer;
