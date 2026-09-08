-- Name: CompleteEditTask
-- Schema: posda_files
-- Columns: []
-- Args: ['new_state', 'from_file_digest', 'to_file_digest', 'edit_task_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Advance a task to its next state and record the file digests.
-- 
-- Clears the lease so the row is no longer reclaimable.

update dicom_edit_task set
  state            = ?,
  from_file_digest = coalesce(?, from_file_digest),
  to_file_digest   = coalesce(?, to_file_digest),
  worker_id        = null,
  lease_expires    = null,
  error            = null,
  updated_at       = now()
where edit_task_id = ?
