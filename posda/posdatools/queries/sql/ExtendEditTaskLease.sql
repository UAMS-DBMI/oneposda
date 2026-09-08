-- Name: ExtendEditTaskLease
-- Schema: posda_files
-- Columns: []
-- Args: ['lease_seconds', 'edit_task_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Heartbeat a lease so a slow file is not reclaimed while in progress.

update dicom_edit_task set
  lease_expires = now() + (? * interval '1 second'),
  updated_at    = now()
where edit_task_id = ?
