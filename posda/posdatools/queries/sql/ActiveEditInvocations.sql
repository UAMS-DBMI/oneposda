-- Name: ActiveEditInvocations
-- Schema: posda_files
-- Columns: ['subprocess_invocation_id', 'current_disposition', 'num_ready']
-- Args: []
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Edit runs a worker should look at, oldest first.
-- 
-- Workers take no arguments and find their own work here, so they can be scaled
-- purely by replica count.
-- 
-- The join against the disposition row is load-bearing, not decoration. While
-- the planner is still streaming tasks in, the run sits at 'Starting Up' and
-- must be invisible: a worker that saw a partially-inserted task list could
-- drain it, observe nothing pending, and declare the whole edit complete while
-- the planner was still writing.
-- 
-- Runs with num_ready = 0 are returned deliberately rather than filtered out.
-- Such a run has no claimable work but has also not been advanced to its next
-- disposition yet -- which is exactly the state left behind when the worker
-- that finished the last file is killed before it can run the transition. If
-- these were filtered out, nothing would ever notice them again and the run
-- would hang at 'Comparisons In Progress' forever. Workers skip the claim step
-- when num_ready is 0 and just re-run the completion check, which is cheap and
-- self-limiting: finalizing moves the run to a disposition not listed here.

select d.subprocess_invocation_id,
       d.current_disposition,
       count(*) filter (
         where t.state in ('pending_edit', 'pending_compare', 'pending_import')
            or ( t.state in ('editing', 'comparing', 'importing')
                 and t.lease_expires < now() )
       ) as num_ready
from dicom_edit_task t
join dicom_edit_compare_disposition d
  on d.subprocess_invocation_id = t.subprocess_invocation_id
where d.current_disposition in
        ('Edits Planned', 'Comparisons In Progress', 'Importing Files')
group by d.subprocess_invocation_id, d.current_disposition
order by d.subprocess_invocation_id
