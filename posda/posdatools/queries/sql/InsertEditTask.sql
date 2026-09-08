-- Name: InsertEditTask
-- Schema: posda_files
-- Columns: ['edit_task_id']
-- Args: ['subprocess_invocation_id', 'sop_instance_uid', 'from_file_id', 'from_path', 'to_path', 'edit_spec']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Insert one file's edit task for a distributed edit run.
-- 
-- Returns no rows when the SOP is already present for this invocation, which is
-- how the planner detects the same SOP appearing in two series without holding
-- every SOP in memory. Also makes re-running the planner idempotent.

insert into dicom_edit_task (
  subprocess_invocation_id, sop_instance_uid, from_file_id,
  from_path, to_path, edit_spec
) values ( ?, ?, ?, ?, ?, ?::jsonb )
on conflict (subprocess_invocation_id, sop_instance_uid) do nothing
returning edit_task_id
