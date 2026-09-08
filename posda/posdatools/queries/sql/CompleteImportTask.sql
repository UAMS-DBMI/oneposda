-- Name: CompleteImportTask
-- Schema: posda_files
-- Columns: []
-- Args: ['to_file_id', 'edit_task_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Record the imported file_id for an edited file and mark it imported.

update dicom_edit_task set
  state         = 'imported',
  to_file_id    = ?,
  worker_id     = null,
  lease_expires = null,
  error         = null,
  updated_at    = now()
where edit_task_id = ?
