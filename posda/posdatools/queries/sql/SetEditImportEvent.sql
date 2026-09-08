-- Name: SetEditImportEvent
-- Schema: posda_files
-- Columns: []
-- Args: ['import_event_id', 'subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Record the import_event the accept phase files its imports under.

update dicom_edit_compare_disposition set
  import_event_id = ?
where subprocess_invocation_id = ?
