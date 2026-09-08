-- Name: GetActivityTaskStatus
-- Schema: posda_files
-- Columns: ['subprocess_invocation_id', 'operation_name', 'start_time', 'last_updated', 'status_text', 'expected_remaining_time', 'end_time', 'since_update', 'stale_warning']
-- Args: ['activity_id']
-- Tags: ['Insert', 'NotInteractive']
-- Description: Activity task status rows for an activity, for the activity UI.
-- stale_warning is non-null when a task has no end_time and has stopped
-- heartbeating, which means the owning process exited without closing itself
-- out -- nothing outside that process ever corrects the row.
-- Not really intended for interactive use
-- 

select
  subprocess_invocation_id,
  operation_name,
  start_time,
  last_updated,
  status_text,
  expected_remaining_time,
  end_time,
  now() - last_updated as since_update,
  case
    when end_time is not null then null
    when last_updated is null then 'never updated'
    when last_updated < now() - interval '5 minutes'
      then 'no status update for ' ||
        date_trunc('second', now() - last_updated)
    else null
  end as stale_warning
from
  activity_task_status natural join subprocess_invocation
where
  activity_id = ? and dismissed_time is null
