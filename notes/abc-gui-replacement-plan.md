# Replace the Posda ActivityBasedCuration GUI

## Context

The Perl GUI is a process-per-app-session system: the controller on 64610 forks a
`SimplifiedAppController.pl` per launch, picks a port from 64615–64630 via a
package-global hash, and nginx has fifteen hard-coded `/paN/` locations. All UI
state is a per-session Perl object graph in process memory; the URL space *is*
the object graph (`/<session>/<Method>?obj_path=…`), the session id is 15 digits of
unseeded `rand()`, the HTTP parser is hand-rolled HTTP/1.0 on a single-threaded
reactor, and the browser polls every 2.5 s and `eval`s returned JS. None of that
can be fixed without replacing `Dispatch::*` / `Posda::HttpApp::*`, which is the
entire framework the 6,832-line `ActivityBasedCuration::Application` sits on.

Only ABC is used. Everything a user does in it ends in one of three sinks:
run a saved query, push a `work` row to Redis, or read activity/inbox tables.
The scripts, saved queries, spreadsheet operations and the Redis/Kueue worker
are the real value and stay untouched.

**Decision: replace ABC with new endpoints in the deployed FastAPI service plus a
React + TypeScript SPA. Run both GUIs side by side until parity is proven, then
remove the launcher and the `/paN/` routes.** Improving in place was rejected
because the defects are the framework, not the application code.

Decisions already taken with the user:

| Topic | Choice |
|---|---|
| Backend | Extend `posda/fastapi` (deployed, owns auth/activities/worker/import routes) |
| Frontend | React 19 + TypeScript, **Vite**, Tailwind 3, served by nginx at `/abc/` |
| Query results | API runs the query, spools JSONL + offset index to the shared cache root, state in a new `query_run` table |
| Non-Postgres saved queries | Support MySQL via **aiomysql** (new dep, approved); `intake` schema needs a DSN (open) |
| Result filter | Case-insensitive regex per column, ANDed, literal fallback on bad pattern (faithful to Perl) |
| Login | New `POST /papi/auth/login` sets `logintoken` as an HttpOnly cookie |
| Scope kept beyond the core | Inbox, Upload To Event, Download (tar), UserAdmin replacement |
| Dropped | QueryEngines builder, LoadedTables/Reports/Tables code, in-process execution, special viewer launchers (keep Mirabelle/Kohlrabi URL links), timeline "resp" button (`subprocess_lines` is empty and nothing writes it) |

## Verified facts that shape the design

- FastAPI uses **asyncpg** with one global pool to `posda_files`
  (`posda/fastapi/app/papi/util/db.py`); `fetch_one` returns `[]` on miss, so test
  `if not row`. Runs as `uvicorn --workers 5`, k8s `replicas: 3`: run state must
  live in Postgres + shared disk, never module globals.
- `posda_files` has `search_path public, dbif_config, dicom_conv`, so
  `queries`, `spreadsheet_operation`, `query_invoked_by_dbif`,
  `user_variable_binding`, `auth.*` are all reachable from the existing pool.
- Saved-query `schema` distribution: 1,466 posda_files/posda_queries, 174
  posda_phi_simple, 80 posda_phi, 59 posda_backlog (dead), 45 `public` (MySQL
  nbia), 22 `intake` (not in databases.json), ~22 others. Runner needs a lazy
  pool registry keyed by `databases.json` alias, read from `POSDA_DATABASE_CONFIG`
  (`/home/posda/databases.json` in k8s, `Config/databases.json` in compose).
- Perl sends every query arg as text and lets PG coerce; asyncpg is strictly
  typed. Runner must `prepare()`, read parameter types, and coerce.
- Redis: tokens are **db 1** (`papi/util/redisqueue.py`), work queues are
  **db 0** (`python/posda/worker/workqueue.py`). Launch service needs its own
  db-0 client.
- Perl GUI already logs in through `POST /papi/auth/token` and sets the
  `logintoken` cookie from JS; FastAPI accepts Bearer or that cookie
  (`auth.py:75-78`). Same token namespace ⇒ SSO with Perl GUI and Mirabelle.
- `auth.apps` row `ActivityBasedCuration` (app_id 13) and `UserAdmin` (1) exist;
  gate the new routes on them via `auth.user_permissions`.
- k8s: `POSDA_CACHE_ROOT=/nas/public/posda/cache2` on the RWX `nas-public` claim,
  mounted on API pods already. Spool sharing works; readers must reopen files per
  request (NFS close-to-open).
- `user_variable_binding` has no unique constraint (dev has 4 rows, no dupes).
- Perl bugs NOT to replicate: bindings fallback reads the wrong hash
  (`NewerProcessPopup.pm:103`); placeholder substitution without `/g` (`:280`);
  `button_name` undefined at launch (`:436`); BackgroundQuery passes the
  spreadsheet file_id as `query_invoked_by_dbif_id`; generated CSV has trailing
  commas and no quoting; query search interpolates user text into `LIKE`.

## Target layout

```
posda/fastapi/app/
  papi/routes/abc/            mounted at /papi/v1/abc  (main.py: include_router(abc.router, prefix="/abc"))
    __init__.py               aggregates; permission dependency (ActivityBasedCuration launch)
    me.py activities.py queries.py query_runs.py operations.py uploads.py
    inbox.py background.py downloads.py admin_users.py
  papi/services/
    db_pools.py               alias -> asyncpg / aiomysql pool from POSDA_DATABASE_CONFIG (lazy, max_size 3)
    workqueue.py              Redis db0 LPUSH + queue length
    bindings.py activities.py inbox.py background_jobs.py downloads.py users_admin.py
    files/ingest.py           import_local_file(conn, path, comment) extracted from routes/importer.py
    queries/{catalog,params,rowstore,runner,filters,csv_export,log}.py
    operations/{catalog,placeholders,resolve,launch,spreadsheets}.py
    workflow_definition.py    port of ABC WorkflowDefinition.pm + ButtonDefinition.pm maps
  tests/                      mirrors services/ and routes/abc/ (pytest, dev DB localhost:5433)
web/abc/                      Vite + React 19 + TS + Tailwind; built with Bun in web/Dockerfile -> /www/abc
database/migrations/          query_run, user_variable_binding unique index, permission seed
```

Reference Perl to port from (read, don't modify):
`posda/posdatools/ActivityBasedCuration/include/ActivityBasedCuration/{Application,WorkflowDefinition,ButtonDefinition}.pm`,
`posda/posdatools/Posda/include/Posda/{NewerProcessPopup,BackgroundQuery,BackgroundList,Inbox,UploadToEvent,ProcessUploadedSpreadsheetWithNoOperation,QueryRowStore,QueryLog}.pm`,
`posda/posdatools/Posda/bin/BottomHalfAsyncQuery.pl`.
Reusable Python: `papi/routes/auth.py` (`get_user_from_database`, `is_valid`,
`logged_in_user`), `papi/routes/activities.py` SQL, `papi/routes/importer.py`
helpers (`create_or_get_file_id`, `copy_file_into_place`, `create_file_location`,
`make_ready_to_process`, `create_import_event`, `create_file_import`),
`papi/util/password.py:encode`, `posdatools/python/posda/queries.py` (reference
only), `posdatools/python/posda/worker/execute.py` (placeholder contract).

## Core designs

### query_run lifecycle (schema change)

```sql
create table query_run (
  query_run_id bigserial primary key,
  query_name text not null, args jsonb not null, caption text not null,
  invoking_user text not null, query_invoked_by_dbif_id integer,
  state text not null check (state in ('queued','running','paused','done','ended','aborted','error','lost')),
  requested_action text check (requested_action in ('pause','resume','abort')),
  owner text, backend_db text, backend_pid integer, is_select boolean,
  row_count integer not null default 0, rows_affected bigint, error_text text,
  spool_dir text not null, filter jsonb, view_filtered boolean not null default false,
  created_at timestamptz not null default now(), started_at timestamptz,
  finished_at timestamptz, last_heartbeat timestamptz, dismissed_at timestamptz
);
create index on query_run (invoking_user, state) where dismissed_at is null;
create index on query_run (state, last_heartbeat);
```

- `start_run` inserts (`queued`), writes `query_invoked_by_dbif` + `dbif_query_args`
  (port of `Posda::QueryLog`), writes args back to bindings, creates
  `$POSDA_CACHE_ROOT/query_runs/<id>/`, then `asyncio.create_task(_execute)` and
  returns. Per-user cap on non-terminal runs (`ABC_MAX_RUNS_PER_USER`, default 5).
- `_execute`: connection from `db_pools.get(schema)`; record `owner=<host>:<pid>`,
  `backend_pid`; selects stream via `cursor(prefetch=1000)` → `rowstore.append_batch`
  in `asyncio.to_thread`; each batch commits `row_count` + `last_heartbeat` (that
  update is the heartbeat) and reads `requested_action` (pause = hold the
  connection and poll 1 s, like Perl held the child; abort = stop). Non-selects
  run `execute` → `rows_affected`, state `done`. Non-select queries stay runnable
  behind a confirm dialog (Perl allowed it).
- Abort from any replica: set `requested_action='abort'` and
  `pg_cancel_backend(backend_pid)` on the `backend_db` pool; owner records `aborted`
  not `error`.
- Janitor task per process competes for `pg_try_advisory_lock`; holder marks
  `running/paused` rows with heartbeat older than 2 min as `lost` (partial rows
  stay pageable) and deletes spool dirs past `ABC_RUN_RETENTION_DAYS` (7) or
  dismissed > 1 day. Replace `main.py`'s `sys.exit(0)` SIGTERM handler with a
  graceful cancel so in-flight runs are marked `aborted`.
- Spool (`rowstore.py`, port of `QueryRowStore.pm`): `rows.jsonl` (JSON array per
  row, ascii), `rows.idx` (`<Q` offset every 256 rows), `meta.json` (columns).
  Readers reopen per request, seek by index, never read past DB `row_count`,
  return `partial: true` if the file lags.
- Filters (`filters.py`): key = sha1(canonical filter + row_count), stored as
  `filter-<key>.jsonl/.idx/.count`; built in a thread by streaming the base store;
  concurrent builders coalesced by file lock. Regex per column, `re.I`, ANDed,
  literal fallback on `re.error`. Filter persisted on the run row.
- CSV (`csv_export.py`): `StreamingResponse`, 1,000 rows per chunk read in a
  thread, reproducing Perl's header: `Metadata:` / `query:,"<caption>"` /
  `when:` / `by:` / `rows:` or `unfiltered_rows:`+`filtered_rows:`+`filter:` /
  blank / `Query Data:` | `Filtered Query Data:` / quoted header / all cells
  quoted, CRLF. Arrays rendered as PG literal `{a,b}` (Perl printed `ARRAY(0x…)`).

### Parameter handling (`queries/params.py`)

- Tokenizer `?` → `$n` that skips single-quoted and dollar-quoted strings and
  `--` / `/* */` comments (the `replace("?", "%s")` in `posda/queries.py` breaks
  on jsonb `?` operators). MySQL path keeps `%s`.
- `stmt = await conn.prepare(sql)`; coerce UI strings per
  `stmt.get_parameters()` type: int/float/numeric/bool/date/timestamp(tz)/arrays;
  interval placeholders rewritten to `$n::text::interval`; empty string → `None`
  for non-text types; text passes through. Fallback if brittle: psycopg 3 async
  (sends `str` as `unknown`, mirrors DBI) — would be a new dep, ask first.

### Operation launch (`operations/`)

- `placeholders.parse(command_line, input_line_format)` → `args` (`<x>`),
  `meta_args` (`<?x?>`), `fields` (from input format), order-preserving, deduped.
  `expand()` replaces **all** occurrences and leaves `<?bkgrnd_id?>` for the worker.
- `resolve.resolve_args(spec, prior_ss_args, current_settings, bindings)`:
  order `prior_ss_args > current_settings (activity_id, latest activity_timepoint_id,
  notify=user, call extras) > bindings > ""`, each value tagged with its source.
  `render_input_lines(spec, rows)` substitutes `<field>` per row, `None → ""`.
- `launch.launch(conn, redis, plan, user)` — one function for every source,
  faithful port of `NewerProcessPopup::StartSubprocess` (`:433-560`):
  1. if no `spreadsheet_file_id`: write a *valid* CSV (`csv` module; header =
     fields + `Operation` + sorted arg names; row 1 carries op + arg values;
     no-input case = blanks + op + args) to `$POSDA_CACHE_ROOT/temp`, import via
     `files/ingest.import_local_file` on the same connection;
  2. `insert spreadsheet_uploaded (now(), true, user, file_id, n_lines)`;
  3. `insert subprocess_invocation (from_spreadsheet, from_button, query_invoked_by_dbif_id, button_name, command_line, spreadsheet_uploaded_id, invoking_user, now(), operation_name) returning id`;
  4. input lines → temp file → import → `input_file_id`;
  5. `worker_priority` from `spreadsheet_operation`;
  6. `insert work (subprocess_invocation_id, input_file_id, background_queue_name) returning work_id`; commit;
  7. `LPUSH work_queue_<p> work_id` on Redis **db 0**; failure after commit → log
     and 502 with ids so it can be re-queued;
  8. return queue length.
- Two-step API: `prepare` returns the editable preview; `launch` re-derives rows
  server-side from `(query_run_id, filtered)` / `file_id` so the client never
  re-uploads row data. Sources: `workflow`, `table` (all working-store rows,
  `button_name` = processing-button caption), `row` (one row as `prior_ss_args`),
  `compare_timepoints` (extras from/to), `spreadsheet` (named: row 1 →
  `prior_ss_args`, `from_spreadsheet=true`, reuse uploaded file_id), background
  query (`RunQueryInBackground.pl <?bkgrnd_id?> "<activity_id>" <query> <notify>`,
  `button_name='background'`, queue 0).
- Candidate operations for an unnamed spreadsheet / "Chain": ops with non-empty
  `input_line_format` whose fields ⊆ columns, ranked by match count desc then
  name (`ProcessUploadedSpreadsheetWithNoOperation.pm:113-135`).

### Bindings and current activity

`GET/PUT /me/bindings` over `user_variable_binding`; selecting an activity PUTs
`activity_id` immediately; query runs and launches write all args back; chained
query links apply their `arg_map` to bindings before opening the target arg form.
Arg-form pre-fill order = Perl `DrawNewQuery`: `activity_id` → current,
`activity_timepoint_id` → latest for current, `notify` → user, else binding, else
blank. Migration: dedupe then unique index on `(binding_user, bound_variable_name)`
so the upsert is `on conflict` (schema change; check prod for duplicates first).

### Login

`POST /papi/auth/login` (JSON) reuses `get_user_from_database` + `is_valid`,
stores the uuid in Redis db 1 like `/token`, responds 204 with
`Set-Cookie: logintoken=…; Path=/; HttpOnly; SameSite=Lax; Secure(if https); Max-Age=3600`.
`POST /papi/auth/logout` deletes the key and clears the cookie. SPA redirects to
`/abc/login?next=` on any 401. Perl GUI's `document.cookie` write becomes a no-op
while the HttpOnly cookie exists (same user's valid token; document in parity notes).

## Phases

Each phase ships against the compose stack with the Perl GUI still at `/posda/`.
Sizes are rough new lines (py / ts). Flagged items: **[schema]**, **[public API]**.

### Phase 1 — Foundations, login, activities, bindings (~700 / 1300)
- **[public API]** `POST /papi/auth/login`, `POST /papi/auth/logout`.
- `GET /abc/me` → `{username, full_name, permissions}`; `GET/PUT /abc/me/bindings`, `PUT /abc/me/bindings/{name}`.
- `GET /abc/activities?include_closed&filter` (`GetOpenActivitiesThirdParty`), `POST /abc/activities {brief_description}`, `PATCH /abc/activities/{id} {third_party_analysis_url}`.
- `GET /abc/activities/{id}/task-status` (+ stale flag after 5 min), `POST …/task-status/{sid}/dismiss`.
- `GET /abc/activities/{id}/timeline` (extend existing `routes/activities.py` query with inbox/email/spreadsheet file ids), `GET …/timepoints` (reuse `get_activity_timepoints`), `GET /abc/files/{id}/text` for email/input viewers.
- **[schema]** `user_variable_binding` unique index migration.
- Infra: `web/abc` Vite scaffold (router basename `/abc`, fetch client with 401 handling), `web/Dockerfile` `abc-builder` stage (bun) + `COPY … /www/abc`, `web/default.conf` `location /abc { alias /www/abc; try_files $uri /abc/index.html; }`, compose dev mounts `./posda/fastapi/app:/fastapi` and `./web/abc/dist:/www/abc`.
- SPA: `LoginPage`, `AppShell` nav, `ActivitiesPage`, `ActivityPage` (`TaskStatusPanel` 3 s poll, `TimelineTable` with overlap count, timepoint from/to radios, `cmp` disabled until Phase 3), `useCurrentActivity` over bindings.
- Tests: `tests/routes/test_auth_login.py` (cookie flags), `tests/services/test_bindings.py`, `test_activities.py` (transaction-rollback fixture); vitest for client 401 flow and timeline overlap.

### Phase 2 — Query catalog and foreground runs (~1900 / 2000)
- `GET /abc/queries/recent` → `{recent[6], frequent[20]}` (`ListOfQueriesPerformedByUserWithLatestAndCount`, selects only).
- `GET /abc/queries/search?args&columns&sql&name` — parameterised (`= any($n)`, `ilike '%'||$n||'%'`).
- `GET /abc/queries/workflow-groups`, `GET /abc/queries/{name}` (+ `chained_links`, `processing_buttons`, `column_links`, `runnable` with reason).
- `POST /abc/query-runs {query_name, args}`; `GET /abc/query-runs?mine`; `GET /abc/query-runs/{id}`; `GET …/rows?first&n&filtered`; `PUT …/filter`; `POST …/{pause|resume|abort|dismiss|rerun}`; `GET …/csv?filtered`.
- `POST /abc/queries/{name}/background` → minimal `operations/launch.py` lands here.
- **[schema]** `query_run` migration. New dep **aiomysql** for `public` schema queries.
- Modules: `db_pools`, `queries/{catalog,params,rowstore,runner,filters,csv_export,log}`, janitor wiring + graceful SIGTERM in `main.py`.
- SPA: `QueriesPage` (Recent / Search / Workflow / Active tabs), `QueryArgForm` (pre-fill rules, date quick buttons, SQL preview, foreground/background), `RunPage` (status banner, filtered/unfiltered radios with counts, per-column filter editor, First row / Show / pg-up / pg-dn, CSV link, row chain links, Mirabelle/Kohlrabi column links), `ActiveRunsTable`.
- Tests: unit `test_params.py` (quoted `?`, `$$`, comments, jsonb `?`), `test_rowstore.py`, `test_filters.py`, `test_csv_export.py`; integration `test_runner.py` on dev DB (`generate_series`, abort via `pg_sleep`, forged-heartbeat `lost`, pause/resume); **differential** `tests/differential/test_csv_parity.py` against Perl-produced CSV fixtures for 3–4 queries captured once from `/pa*/…DownloadCurrentForegroundQuery` (normalise `when:`).

### Phase 3 — Operations, chaining, spreadsheet upload (~1400 / 1500)
- `GET /abc/operations?q&tags`, `GET /abc/operations/{name}` (+ parsed args/meta/fields, `program_found` via `shutil.which`).
- `GET /abc/workflow/categories` (ported `@ActivityCategories`).
- `POST /abc/operations/prepare` and `POST /abc/operations/launch` with the tagged-union source body; `GET /abc/operations/candidates?query_run_id|file_id`.
- `POST /abc/uploads` (multipart → stored under `$POSDA_CACHE_ROOT/abc_uploads/<user>/<uuid>/`, imported via `files/ingest`), `GET /abc/uploads/{file_id}/sheet` → `{columns, first_row, row_count, operation|null}` (CSV via `csv`, XLSX via `xlsx2csv` already in the image). Zip/tar uploads expanded server-side (port of `ExtractUpload.pl` behaviour).
- Behaviour-preserving refactor: move importer helpers into `services/files/ingest.py`, importer route calls them (own commit).
- SPA: `WorkflowPage` (15 steps, operation buttons, query-group links, operation picker datalist), `LaunchDialog` (summary, outdated warning, editable args with source badges, live expanded command, input head/tail preview, Start → queue length), table/row buttons on `RunPage`, "Chain" → `CandidateOperationsTable`, `UploadPage` (dropzone, per-file row, chain named/unnamed, Annotation shortcut = `InsertListOfAnnotatedFiles`), enable timeline `cmp`.
- Tests: `test_placeholders.py` (meta args, duplicates, `/g`), `test_resolve.py` (order, bindings used), `test_spreadsheets.py` (Operation detection, ranking); integration `test_launch.py` on dev DB with an injected Redis stub asserting `LPUSH`, rows in `spreadsheet_uploaded` / `subprocess_invocation` / `work`, CSV content; e2e smoke: launch `AddFilesToTimepoint` with 0 lines, confirm compose worker finishes it.

### Phase 4 — Inbox, background jobs, download, upload-to-event (~700 / 900)
- `GET /abc/inbox?include_dismissed`, `GET /abc/inbox/unread-count` (10 s poll), `GET /abc/inbox/{id}`, `POST …/{read|dismiss}`, `POST …/forward {username}`, `POST …/file {activity_id}` (InsertActivityInboxContent + dismiss), `GET /abc/inbox/users`. SQL verbatim from `Posda::Inbox`.
- `GET /abc/background-jobs?mode=all|running|errored|finished&in_last` (`GetBackgroundJobs*` queries, 100-row cap + total); file links via existing `/papi/v1/files/{id}/data`.
- `GET /abc/downloads`, `GET /abc/downloads/{name}/tar` (stream `tar -chf - .` via `asyncio.create_subprocess_exec`; name validated), `DELETE /abc/downloads/{name}`.
- Upload To Event: SPA-only over existing `PUT /papi/v1/import/event` + `/import/file` (same flow as `web/www/upload.html`).
- SPA: `InboxPage`, `InboxItemPage`, nav badge, `BackgroundJobsPage`, `DownloadsPage`, `UploadToEventPage`.
- Tests: `test_inbox.py`, `test_downloads.py` (traversal rejected, tar contents).
- Forward-email notification only when `POSDA_REAL_EMAIL=1` (shell `mail` like Perl), otherwise skipped.

### Phase 5 — User admin, permission gating, hardening (~500 / 500)
- `GET/POST /abc/admin/users`, `PATCH /abc/admin/users/{id}` (password via `password.py:encode`), `GET /abc/admin/apps`, `GET /abc/admin/permissions`, `PUT /abc/admin/users/{id}/permissions`; gated on `UserAdmin` app permission.
- Permission dependency on every `/abc` route (`ActivityBasedCuration`). **[schema]** seed migration only if a needed permission row is missing on prod.
- Login rate limit (Redis counter), `ABC_*` settings module, structured run-lifecycle logging, `GET /abc/status` (runs by state, spool bytes).
- SPA: `AdminUsersPage`, permission-aware nav.

### Phase 6 — Parity verification and cutover (config, ~200 lines)
1. `web/abc/docs/PARITY.md` checklist walked by a curator with both GUIs; re-run CSV fixtures; diff `prepare` previews against Perl rendered command lines for ~20 operations (all with meta-args, all `special`).
2. Soak: Perl post-login landing redirects to `/abc/` (one line in `Posda/include/Posda/HttpApp/JavaScriptApp.pm`).
3. Decommission: `web/default.conf` + `deployment-manifests/posda/config/web.conf` drop `/pa1/…/pa15/`, `/posda/` → `302 /abc/`, drop `posda-error.html` mount; `posda_start.sh` / `bin/shell_library.sh` stop launching `AppController.pl` (read first; the `posda` service also hosts the dead receiver on 11112); k8s `apps/posda.yaml` drop 64610/646xx ports; `config/api.env` gains `ABC_*`; `apps/web.yaml` image bump.
4. Delete after `grep -r` confirms no `use`: `ActivityBasedCuration/`, `DbIf/`, UserAdmin app, `Posda/include/Posda/HttpApp/*`, `Posda/include/Posda/{NewerProcessPopup,BackgroundQuery,BackgroundList,UploadToEvent,ProcessUploadedSpreadsheetWithNoOperation,PopupWindow,Popup*,QueryRowStore}.pm`, `Dispatch/TopHalfAsyncQuery.pm`, `Posda/bin/BottomHalfAsyncQuery.pl`, `Posda/bin/AppController/*`, `Posda/bin/SimplifiedAppController.pl`, `ExtractUpload.pl`, `CsvToPerlStruct.pl`.
   Keep: `Posda/bin/*` operation scripts, `Posda::BackgroundProcess`, `Posda::Inbox` (scripts call `SendMail`), `Posda::QueryLog` (`RunQueryInBackground.pl`), `Posda::DB`, `PosdaDB::Queries`, `Posda::File::Import`, `queries/`, `spreadsheet_operations/`, `python/posda/worker`, `FastFileProcessDaemon.pl`, `Dispatch::Select` if the daemon uses it (verify).

## Dependencies to add (ask before adding anything else)

- Python: `aiomysql` (approved for MySQL saved queries). Optional later: `psycopg[binary]` only if asyncpg coercion proves brittle; `fakeredis` for tests (otherwise a 20-line stub).
- `web/abc` (new project): `react`, `react-dom`, `react-router-dom@7`, `typescript`, `vite`, `@vitejs/plugin-react`, `tailwindcss@3`, `swr` (Mirabelle precedent), `vitest`, `@testing-library/react`, `jsdom`.

## Resolved questions and remaining defaults

- Deployed image is `registry.dbmi.cloud/posda` 1.1.x, which ships Python 3.14+.
  The local compose stack is switched to that image for every posda service so
  dev matches prod.
- LDAP is not needed. FastAPI's `auth.users` check is the only authentication.
- `intake` schema DSN for its 22 queries: default `runnable: false` with a reason
  until a DSN is supplied.
- Pause/resume holds a pool connection while paused: keep (faithful; pool
  `max_size` bounds it).

## Verification

- Dev stack: `docker compose up` at repo root; dev DB `localhost:5433` (`postgres/example`); API at `http://localhost/papi`, SPA at `http://localhost/abc/`, Perl GUI at `http://localhost/posda/`.
- `uv run pytest` under `posda/fastapi` for every phase (unit + dev-DB integration); `bun run test` (vitest) under `web/abc`.
- Phase 2: differential CSV parity test vs Perl fixtures; manual check that Active tab shows a run started in one API worker from a request served by another (hit the API several times; `owner` differs).
- Phase 3: launch an operation from each source (workflow button, table, row, upload named/unnamed, compare timepoints, background query) and confirm the compose worker runs it (`work.status='finished'`, report appears on the timeline).
- Phase 6: curator walkthrough of `PARITY.md`; after decommission, `curl -I http://localhost/pa1/` returns 404 and `/posda/` redirects to `/abc/`.
