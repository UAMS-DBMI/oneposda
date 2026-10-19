-- Foreground query runs for the ActivityBasedCuration replacement.
--
-- The Perl GUI kept each foreground query in the memory of the per-session
-- app server process. The API runs with several worker processes and
-- replicas, so a run's state lives here and its rows are spooled under
-- $POSDA_CACHE_ROOT/query_runs/<query_run_id>/ on the shared cache volume.
-- Any process can then page, filter, download, pause or abort a run.

create table if not exists query_run (
  query_run_id bigserial primary key,
  query_name text not null,
  args jsonb not null,
  caption text not null,
  invoking_user text not null,
  query_invoked_by_dbif_id integer,
  state text not null
    check (state in ('queued', 'running', 'paused', 'done', 'ended',
                     'aborted', 'error', 'lost')),
  requested_action text
    check (requested_action in ('pause', 'resume', 'abort')),
  owner text,
  backend_db text,
  backend_pid integer,
  is_select boolean,
  row_count integer not null default 0,
  rows_affected bigint,
  error_text text,
  spool_dir text not null,
  filter jsonb,
  view_filtered boolean not null default false,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  last_heartbeat timestamptz,
  dismissed_at timestamptz
);

create index if not exists query_run_user_open_idx
  on query_run (invoking_user, state)
  where dismissed_at is null;

create index if not exists query_run_state_heartbeat_idx
  on query_run (state, last_heartbeat);
