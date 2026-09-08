-- Name: EditTaskStateCounts
-- Schema: posda_files
-- Columns: ['state', 'num_tasks']
-- Args: ['subprocess_invocation_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Count edit tasks by state for one edit run.
-- 
-- Replaces the in-memory counters the old single-process editor kept in its
-- Editor object, so progress survives a restart and is the same regardless of
-- which worker asks.

select state, count(*) as num_tasks
from dicom_edit_task
where subprocess_invocation_id = ?
group by state
order by state
