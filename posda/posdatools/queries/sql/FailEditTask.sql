-- Name: FailEditTask
-- Schema: posda_files
-- Columns: []
-- Args: ['new_state', 'error', 'edit_task_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Move a task to a terminal failure state with its error text.

update dicom_edit_task set
  state         = ?,
  error         = ?,
  worker_id     = null,
  lease_expires = null,
  updated_at    = now()
where edit_task_id = ?
