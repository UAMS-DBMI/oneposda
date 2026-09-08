-- Name: ReleaseEditTask
-- Schema: posda_files
-- Columns: []
-- Args: ['pending_state', 'edit_task_id']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Return a claimed but unstarted task to its pending state.
-- 
-- Used on SIGTERM so a scaled-down worker hands work back immediately instead
-- of making the next worker wait out the lease. The attempt is given back too:
-- a graceful release is not a failed attempt and must not count against the
-- poison-pill budget.

update dicom_edit_task set
  state         = ?,
  worker_id     = null,
  lease_expires = null,
  attempts      = greatest(attempts - 1, 0),
  updated_at    = now()
where edit_task_id = ?
