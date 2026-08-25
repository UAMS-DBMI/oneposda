-- activity_task_status had no primary key, no unique constraint and no index
-- at all. Every heartbeat -- one UPDATE ... WHERE activity_id = ? AND
-- subprocess_invocation_id = ? per running background task, every 10 seconds --
-- was a sequential scan, and nothing stopped duplicate rows for one task.
--
-- This adds the index only, deliberately. A primary key on (activity_id,
-- subprocess_invocation_id) is what the table actually wants, but existing
-- deployments may already hold duplicates and ADD PRIMARY KEY would then fail
-- mid-deploy. Check with:
--
--   select activity_id, subprocess_invocation_id, count(*)
--   from activity_task_status
--   group by 1, 2 having count(*) > 1;
--
-- and promote this to a primary key in a follow-up migration once that comes
-- back empty on every deployment.
CREATE INDEX IF NOT EXISTS activity_task_status_key_idx
    ON public.activity_task_status USING btree
    (activity_id, subprocess_invocation_id);

-- Supports finding tasks that have stopped heartbeating: a row with no
-- end_time whose last_updated has gone stale means the process died without
-- closing itself out. Nothing outside the owning process ever corrects that.
CREATE INDEX IF NOT EXISTS activity_task_status_open_idx
    ON public.activity_task_status USING btree (last_updated)
    WHERE end_time IS NULL;
