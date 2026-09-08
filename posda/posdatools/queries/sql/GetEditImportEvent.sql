-- Name: GetEditImportEvent
-- Schema: posda_files
-- Columns: ['import_event_id', 'dest_dir']
-- Args: ['subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: The import_event and temp directory for an edit run.

select import_event_id, dest_dir
from dicom_edit_compare_disposition
where subprocess_invocation_id = ?
