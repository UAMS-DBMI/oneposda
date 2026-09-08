-- Name: SeedImportTasks
-- Schema: posda_files
-- Columns: []
-- Args: ['subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Queue every compared file for import in one statement.
-- 
-- Resets attempts so a file that needed retries during the edit phase starts
-- the import phase with a full poison-pill budget.

update dicom_edit_task set
  state         = 'pending_import',
  attempts      = 0,
  worker_id     = null,
  lease_expires = null,
  error         = null,
  updated_at    = now()
where subprocess_invocation_id = ?
  and state = 'compared'
