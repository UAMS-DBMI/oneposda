-- Name: EditTaskErrorsForEdit
-- Schema: posda_files
-- Columns: ['sop_instance_uid', 'state', 'attempts', 'error', 'from_path']
-- Args: ['subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Tasks that ended in a failure state, for the errors report.

select sop_instance_uid, state, attempts, error, from_path
from dicom_edit_task
where subprocess_invocation_id = ?
  and state in ('edit_failed', 'compare_failed', 'import_failed')
order by sop_instance_uid
