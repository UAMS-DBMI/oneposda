-- Name: OrphanToFilesForEdit
-- Schema: posda_files
-- Columns: ['to_file_id', 'from_file_id', 'sop_instance_uid']
-- Tags: ['for_scripting', 'dicom_edit']
-- Args: ['subprocess_invocation_id', 'old_activity_timepoint_id']
-- Description: Edited files whose source file was not in the timepoint being replaced.
-- 
-- The set the old code arrived at by deleting from %InverseConversionsInNewTimepoint
-- as it walked the timepoint, and reported as an error spreadsheet if non-empty.

select t.to_file_id, t.from_file_id, t.sop_instance_uid
from dicom_edit_task t
where t.subprocess_invocation_id = ?
  and t.state = 'imported'
  and not exists (
    select 1
      from activity_timepoint_file atf
     where atf.activity_timepoint_id = ?
       and atf.file_id = t.from_file_id
  )
order by t.to_file_id
