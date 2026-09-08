-- Name: UpdateEditProgressCounts
-- Schema: posda_files
-- Columns: []
-- Args: ['number_edits_scheduled', 'number_compares_with_diffs', 'number_compares_without_diffs', 'subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Update only the progress counters on a disposition row.
-- 
-- Deliberately does NOT write current_disposition. UpdateDicomEditCompareDisposition
-- sets it to 'Comparisons In Progress' in the same statement, which races its own
-- finalizer and can clobber a state that ImportEditsTp.pl just claimed via CAS.
-- State transitions belong to Posda::EditStateChange::Trans and nothing else.

update dicom_edit_compare_disposition set
  number_edits_scheduled        = ?,
  number_compares_with_diffs    = ?,
  number_compares_without_diffs = ?,
  last_updated                  = now()
where subprocess_invocation_id = ?
