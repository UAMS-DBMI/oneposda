-- Name: ClaimEditTasks
-- Schema: posda_files
-- Columns: ['edit_task_id', 'sop_instance_uid', 'from_path', 'to_path', 'edit_spec', 'from_file_digest', 'to_file_digest', 'from_file_id', 'attempts']
-- Args: ['new_state', 'worker_id', 'lease_seconds', 'subprocess_invocation_id', 'pending_state', 'stale_state', 'batch_size']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Atomically claim a batch of edit tasks for one worker.
-- 
-- FOR UPDATE SKIP LOCKED lets any number of workers claim disjoint batches
-- concurrently without blocking each other. Rows already in stale_state whose
-- lease_expires has passed are reclaimed by the same statement, so a worker
-- killed with SIGKILL needs no reaper to recover its work.
-- 
-- Must be run with FetchResults, not RunQuery: RunQuery decides select-mode by
-- regex on the leading keyword and would return the row count instead of the
-- RETURNING rows.

update dicom_edit_task
   set state         = ?,
       worker_id     = ?,
       attempts      = attempts + 1,
       lease_expires = now() + (? * interval '1 second'),
       updated_at    = now()
 where edit_task_id in (
   select edit_task_id
     from dicom_edit_task
    where subprocess_invocation_id = ?
      and ( state = ?
            or ( state = ? and lease_expires < now() ) )
    order by edit_task_id
      for update skip locked
    limit ?
 )
returning edit_task_id, sop_instance_uid, from_path, to_path,
          edit_spec, from_file_digest, to_file_digest, from_file_id, attempts
