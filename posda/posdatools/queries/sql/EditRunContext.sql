-- Name: EditRunContext
-- Schema: posda_files
-- Columns: ['activity_id', 'user_to_notify', 'dest_dir', 'import_event_id']
-- Args: ['subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: The activity, notify target and temp directory of an edit run.
-- 
-- A worker knows only the subprocess_invocation_id it picked up, but has to
-- pass the activity and notify target on to the report and timepoint jobs it
-- queues. Both were recorded when the planner created its background process.

select ats.activity_id,
       bs.user_to_notify,
       d.dest_dir,
       d.import_event_id
from dicom_edit_compare_disposition d
left join activity_task_status ats
  on ats.subprocess_invocation_id = d.subprocess_invocation_id
left join background_subprocess bs
  on bs.subprocess_invocation_id = d.subprocess_invocation_id
where d.subprocess_invocation_id = ?
