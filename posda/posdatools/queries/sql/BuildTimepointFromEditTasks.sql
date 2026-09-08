-- Name: BuildTimepointFromEditTasks
-- Schema: posda_files
-- Columns: []
-- Args: ['new_activity_timepoint_id', 'subprocess_invocation_id', 'old_activity_timepoint_id']
-- Tags: ['for_scripting', 'dicom_edit', 'activity_timepoint_support']
-- Description: Populate a new activity timepoint from an old one, substituting edited files.
-- 
-- Replaces the per-file Perl loop in ImportEditsTp.pl, which ran one insert AND
-- one activity_task_status update for every file in the timepoint. Files that
-- were edited come across as their edited file_id, everything else is carried
-- over unchanged.
-- 
-- The distinct matches the old loop's source query (FilesInTimepoint selects
-- distinct file_id) and additionally collapses the case where two source files
-- edit to byte-identical content and therefore share one file_id.

insert into activity_timepoint_file (activity_timepoint_id, file_id)
select ?, f.file_id
from (
  select distinct coalesce(t.to_file_id, atf.file_id) as file_id
    from activity_timepoint_file atf
    left join dicom_edit_task t
      on  t.subprocess_invocation_id = ?
      and t.from_file_id             = atf.file_id
      and t.state                    = 'imported'
   where atf.activity_timepoint_id = ?
) f
