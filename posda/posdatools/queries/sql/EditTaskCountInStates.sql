-- Name: EditTaskCountInStates
-- Schema: posda_files
-- Columns: ['num_tasks']
-- Args: ['subprocess_invocation_id', 'states']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Count tasks for one edit in any of the given states.
-- 
-- states is a Postgres text array, e.g. '{pending_edit,editing}'. Used for the
-- "is this phase drained?" check that decides who advances the disposition.

select count(*) as num_tasks
from dicom_edit_task
where subprocess_invocation_id = ?
  and state = any (?::text[])
