# Posda (posdatools) — Architecture Notes

Notes from a read-through of `posda/posdatools` as of 2026-08-10 (master, at
`01b33621`). Describes how the legacy Perl system is instantiated, configured,
and structured, and which parts are still live.

> **Status legend used throughout**
> **[LIVE]** — in the active path today
> **[DEAD]** — code still present, no longer used; kept for context so nobody
> re-derives it from scratch or "fixes" something that isn't running

---

## 1. What it is

Posda — "Perl Open Source DICOM Archive" — is the legacy core of the TCIA
curation pipeline. Copyright headers date to 2008 (Bill Bennett), licensed
Artistic/GPL.

Rough scale:

| Kind | Count |
|---|---|
| `.pl` scripts | 1,043 |
| `.pm` modules | 340 |
| `.sql` files | 2,028 |
| `.py` files | 113 |
| `.row` spreadsheet ops | 259 |
| Total files | ~5,095 |

It is **not** a PACS. It is a curation workbench: ingest DICOM, shred every
attribute into a relational schema, then run analyst-driven queries, PHI scans,
anonymization edits, and visual review before pushing data out to NBIA/TCIA.

---

## 2. Configuration

Three layers, all rooted in environment variables.

### 2.1 Shell environment

`posda.env` (copied from `posda.env.example`) exports `POSDA_*` variables:
`POSDA_ROOT`, `POSDA_CACHE_ROOT`, `POSDA_PORT` (64610), `POSDA_DATABASE_CONFIG`,
`POSDA_API_URL`, `POSDA_AUTH_TYPE`, etc.

`Config/SetEnv` sources it, prepends `bin/` to `PATH`, and then auto-discovers
installed apps:

```bash
for i in **/env/Setup; do
  NAME=$(dirname $(dirname $i))
  source $i $APP_CONTROLLER_ROOT/$NAME
done
```

Each app's `env/Setup` appends its own `include/` to `PERL5LIB` and its `bin/`
to `PATH`. **That glob is the entire plugin mechanism** — dropping a directory
with an `env/Setup` in it registers a new app's code paths.

### 2.2 `Posda::Config`

`Posda/include/Posda/Config.pm`. `Config('foo')` reads `$ENV{POSDA_FOO}`, with
a `$loading_rules` table for computed values:

| Key | Derivation |
|---|---|
| `databases` | parsed from `$POSDA_DATABASE_CONFIG` (`Config/databases.json`) |
| `dicom_send_locations` | `Config/dicom_send_locations.json` |
| `extraction_mgr_port` | `port + 2` |
| `port_pool` | `(port+5) .. (port+20)` → **64615–64630** |

`Database('posda_files')` builds a DBI DSN string from the same JSON.

### 2.3 Per-app JSON

`Posda::ConfigRead->new($dir)` slurps every `*.json` in a config directory into
`$HTTP_APP_CONFIG->{config}->{<basename>}`. Two quirks:

1. It strips `//` comment lines before parsing — JSON doesn't permit them, and
   these files are full of them. It also sets `$json->relaxed(1)` for trailing
   commas.
2. It does a **blind textual substitution of every `POSDA_*` env var name
   against the raw file text**. That is how `"POSDA_ROOT/HttpRoot/http_root"`
   becomes a real filesystem path. It is a plain `s///g` on variable *names*, so
   any literal occurrence of the string is replaced regardless of context.

Config directories: `Config/AppConfig` (the main controller) plus one per app
(`Config/DbIf`, `Config/UserAdmin`, `Config/ActivityBasedCuration`, …). Each
typically holds `Environment.json` (init class/method, HTTP root), and
`Identity.json` (branding, window size).

---

## 3. Instantiation

### 3.1 Startup chain

```
posda.service  ──▶ posda_start.sh
                     └─▶ bin/shell_library.sh :: start_foreground
                           └─▶ AppController.pl <host> <port> Config/AppConfig
```

`Posda/bin/AppController/AppController.pl`:

1. `Posda::ConfigRead->new($dir)` → `$HTTP_APP_CONFIG`
2. Reads `Environment.json` for `ApplicationInitClass`
   (`AppController::JavaScriptApp`), `ApplicationInitMethod` (`InitApp`),
   `ApplicationLoginMethod` (`NullLogin`)
3. `eval "require $class"` — runtime string eval, not a compile-time `use`
4. `GetMethodRef("Posda::HttpObj", $method, \%main::, "")` — walks the Perl
   **symbol table by hand** to turn `Posda::HttpObj::InitApp` into a coderef
5. Instantiates `StaticObjs` from `Applications.json` **[DEAD]** — the only
   entry is `Posda::Receiver` on DICOM port 11112 (see §6.2)
6. Builds `Dispatch::Http::App::Server`, calls `->Serve($port, 10, 60)`
7. Installs TERM/ABRT/QUIT/HUP handlers that tear down sessions and dump the
   dispatch table
8. `Dispatch::Select::Dispatch()` — enters the event loop, never returns

### 3.2 Docker (the real deployment) [LIVE]

systemd unit files under `systemd/service-files/` are the older path and still
hardcode `/home/posda/posdatools`. Production runs from
`config/docker-compose.yaml` instead.

One image, `tcia/posda:1.0.4`, with `posda/docker-entrypoint` dispatching on
argv:

| Command | Runs | Status |
|---|---|---|
| `main` | `posda_start.sh` → AppController | **[LIVE]** |
| `api` | `/start_api.sh` → FastAPI | **[LIVE]** |
| `worker` | `worker_start.sh` → `WorkerNode.py` | **[LIVE]** |
| `file-process` | `Posda/bin/FastFileProcessDaemon.pl` | **[LIVE]** |
| `backlog-process` | `Posda/bin/ProcessBacklog.pl` | **[DEAD]** — supported by the entrypoint but no compose service defines it |

First run of `main` detects a missing `/home/posda/cache/POSDA_VERSION`, runs
`setup.sh`, and seeds `file_storage_root` with four roots (`submission_root`,
`k-storage`, `created`, and a browser-import root).

Compose services: `db` (Postgres 13.7, exposed on **5433**), `redis`, `posda`,
`posda-api`, `posda-worker-low` (priority 0), `posda-worker-high` (priority 1),
`posda-fast-file-process`, `steve` (cron-ish job runner), `thumbs` + `magicka`
(lanterna image), `kaleidoscope`, `web` (nginx). `ream` and `exodus` are
commented out.

Note the compose file bind-mounts `./posda/posdatools` over the image's copy, so
the running code is the working tree, not what was baked into the image.

### 3.3 nginx routing

`web/default.conf` fronts everything on 80/443:

| Path | Upstream |
|---|---|
| `/posda/` | `posda:64610` (main controller) |
| `/pa1/` … `/pa15/` | `posda:64615` … `posda:64629` (sub-app processes) |
| `/papi/` | `posda-api:8087` (FastAPI) |
| `/files/` | `/home/posda/cache/`, gated by `auth_request` |
| `/k`, `/viewer`, `/ohif`, `/mira`, `/kohlrabi`, `/dashboard`, `/roots` | static SPAs |

`/auth-check` is an internal `auth_request` subrequest to
`/papi/auth/users/me`, cached 30s keyed on the Authorization header + cookie.

---

## 4. The web layer

### 4.1 Event loop

`Posda/include/Dispatch/Select.pm` — a hand-rolled single-threaded reactor over
`IO::Select`. State lives in file-scoped hashes: `$readers`, `$writers`,
`$excepts` (keyed by fileno), plus a `$background` queue and a `$timer` hash
keyed by absolute wake time. Everything registered is a closure blessed into
`Dispatch::Select::Socket`, `::Background`, or `::Event`.

`Dispatch()` loops: compute the next timer delta, `select()` with that timeout,
dispatch ready fds, then drain up to `$MaxBackgrounds` (100) background
closures. Returns only when nothing at all is registered.

### 4.2 URL space is the Perl method namespace

`Dispatch::Http` layers HTTP on top. The scheme:

```
/<session_id>/<MethodName>?obj_path=<ObjectPath>&param=value
```

`AppDispatch` pulls `session_id` from the first path segment, verifies it exists
in `{Inventory}` and is `logged_in`, then `DispatchObj` looks up
`$sess->{root}->{$obj_path}` and calls:

```perl
$obj->$method($http, \%env);
```

So a URL directly names a Perl object and one of its methods. Per-session
server-side object graphs hold **all** UI state — this is a stateful
continuation-style server, not request/response MVC.

Rendering: `RefreshEngine($http, $dyn, $template)` expands
`<?dyn="Widget" arg="x"?>` markers, each of which recursively invokes another
method on the object. Base class is
`Posda/include/Posda/HttpApp/HttpObj.pm` (82 KB);
`HttpApp/JsController.pm` (53 KB) drives the browser via
`PosdaGetRemoteMethod(op, params, callback)` AJAX calls.

### 4.3 Process-per-app-session

The controller on 64610 is primarily a launcher.
`AppController::JavaScriptApp::LaunchApp` →
`GetAvailableSockets` picks an unused port from `Config('port_pool')` →
`AppController::JsChildProcess` `fork`s and `exec`s a **separate
`SimplifiedAppController.pl` process** for that app, with its own config
directory and a hashed token.

`$port_mapper` in both controllers maps 64615–64629 to `pa1`…`pa15`, which is
what nginx proxies. Consequently each user's each app session is its own OS
process — hence `Restart=always` and the `error_page 502 /posda-error.html`
fallback in nginx.

**Config gotcha:** the `SocketPool` array in
`Config/AppConfig/Applications.json` (64665+) is **ignored**. The pool actually
used is `Posda::Config`'s computed `port_pool` (64615–64630), which is what
`$port_mapper` and nginx agree on.

### 4.4 Registered apps

From `Config/AppConfig/Applications.json`, each paired with a `Config/<App>/`
directory:

| App | Entry | Notes |
|---|---|---|
| **DbIf** | `SimplifiedAppController.pl` | The main workhorse. `DbIf/include/DbIf/Application.pm` is 188 KB |
| ActivityBasedCuration | `SimplifiedAppController.pl` | Activity-centric curation |
| UserAdmin | `SimplifiedAppController.pl` | |
| Kaleidoscope | `kaleidoscope.pl` | Series projection review |
| DicomProxy | `AppController.pl` | |
| GenericApp / NewGenericApp | `SimplifiedAppController.pl` | |
| NewItcTools | `AppController.pl` | |
| DicomLookup | — | commented out |

---

## 5. Databases

12 Postgres databases declared in `Config/databases.json`, plus one MySQL entry
pointing at an external NBIA instance.

`posda_files` is the heart: **252 tables** across schemas `public`, `auth`,
`dbif_config`, `dicom_conv`, `db_version`.

### 5.1 Core file model

```
file (file_id, digest, size, is_dicom_file, file_type,
      processing_priority, ready_to_process)
  │
  ├── file_location (file_id, file_storage_root_id, rel_path, file_is_present)
  │        └── file_storage_root (root_path, current, storage_class)
  │
  ├── file_import (import_event_id, file_id, rel_path, file_import_time)
  │        └── import_event (import_type, importing_user, import_time, …)
  │
  └── dicom_file (dataset_digest, xfr_stx, has_meta, dicom_file_type,
                  pixel_data_digest, pixel_data_offset, pixel_data_length)
```

Storage is content-addressed on disk under `POSDA_CACHE_ROOT`, with
`file_storage_root` mapping storage classes to roots.

### 5.2 DICOM shredded by module

`file_meta`, `file_patient`, `file_study`, `file_series`, `file_image`,
`file_sop_common`, `file_equipment`, `file_image_geometry`,
`file_slope_intercept`, `file_win_lev`, `file_ct_image`, `file_mr`,
`file_pt_image`, `file_dose`, `file_plan`, `file_structure_set`, `file_for`,
`file_nifti`, plus RT detail tables (`beam_*`, `control_point_*`,
`contour_image`, `image_*`).

Every parsed attribute lands in a typed column. This is what makes the
query-driven curation workflow possible.

### 5.3 Workflow tables

- `activity`, `activity_timepoint`, `activity_timepoint_file`,
  `activity_posda_file`, `activity_task_status`, `activity_inbox_content` —
  the **activity** is the unit of curation work
- `subprocess_invocation`, `background_subprocess`,
  `background_subprocess_params`, `background_subprocess_report`,
  `background_input_line` — job tracking
- `visual_review_instance` — masking / visual QA
- `auth.users`, `auth.apps`, `auth.permissions`, `auth.user_permissions`
- `dbif_config.*` — query tabs, roles, popup/background buttons,
  `spreadsheet_operation`

### 5.4 Other databases

`posda_auth`, `posda_appstats`, `posda_nicknames`, `posda_counts`, `posda_phi`,
`posda_phi_simple`, `private_tag_kb`, `public_tag_disposition`, `dicom_roots`,
`dicom_dd`, and **`posda_backlog` [DEAD]**.

`Posda/sql/private_tag_kb_data.sql` (2.7 MB) and `posda_phi_simple_data.sql`
(566 KB) are seeded knowledge bases, not schema.

---

## 6. Ingest

### 6.1 Live path [LIVE]

```
HTTP upload / import_files.pl / disk scan
        ↓
file rows created, ready_to_process = true, processing_priority set
        ↓
FastFileProcessDaemon.pl        (compose: posda-fast-file-process)
        ↓
Posda::Try → Posda::Dataset / Posda::Parser   (pure-Perl DICOM parser)
        ↓
dicom_file + all file_* module tables populated
```

`NewProcessFilesInDb.pl` is the per-chunk worker; it selects files where
`is_dicom_file is null and ready_to_process and processing_priority is not
null`, ordered by priority, `limit ?`.

**Leader election is a database-row mutex.** `import_control.status` cycles
`waiting to go inservice` → `service process running` with `processor_pid`;
shutdown is requested by setting `pending_change_request = 'shutdown'`. The
older `PosdaFileProcessDaemon.pl` implements the same loop and shells out to
`NewProcessFilesInDb.pl` in chunks.

### 6.2 DICOM receive pipeline [DEAD]

**No longer used.** Retained in the tree:

- `Posda::Receiver` — declared as a `StaticObj` on port 11112 in
  `Applications.json`; still instantiated at AppController startup
- `Dispatch::Dicom::{Assoc,Storage,Finder,Verification,MessageAssembler,…}`
  and `Posda::Ae::{AssocRq,AssocAc,AssocRj,AssocAbort,AssocRelease,Negotiation,
  LocalServer}` — the association state machine
- `PosdaReceiveDaemon.pl`, `dicom_receive_process_daemon.py`,
  `posda-receive.service`, `POSDA_RECIEVER_PORT` / `POSDA_RECEIVE_DAEMON_PORT`
- `association*` tables in `posda_files`

Port 11112 is still published by the compose file.

### 6.3 Backlog processor [DEAD]

**The `posda_backlog` database is no longer used.** Dead alongside it:
`ProcessBacklog.pl`, `systemd/{start,stop}_ProcessBacklog.pl`,
`posda-backlog.service`, the `backlog-process` entrypoint command, the
`control_status` leader-election table, and `Posda/sql/posda_backlog*.sql`
(still listed in `Config/databases.json`).

---

## 7. Queries and operations live in the database

The most consequential design decision in the system.

### 7.1 Named queries

SQL lives as **rows in the `queries` table** of `posda_files`:
`(name, query, args, columns, tags, schema, description)`.

Both languages resolve the same names:

```perl
Posda::DB::Query("GetPosdaFilesImportControl")->RunQuery($row_cb, $end_cb, @args);
```
```python
posda.queries.Query("GetPosdaFilesImportControl").run(**kwargs)
```

The Perl side (`PosdaDB::Queries`) caches DBI handles per connect string and
logs each retrieval into `query_log`. The Python side (`posda/queries.py`)
rewrites `?` placeholders to `%s` and picks the database from the query's
`schema` column.

### 7.2 Disk mirror

`queries/sql/*.sql` — **1,868 files** — is a *mirror*, with metadata carried in
comment headers:

```sql
-- Name: SomeQuery
-- Schema: posda_files
-- Columns: ['a', 'b']
-- Args: ['x']
-- Tags: ['import']
-- Description: ...

select ...
```

`queries/import.py`, `export.py`, `list.py`, `clean.py` sync in both
directions; `SyncAllQueries` reconciles drift via `FindMissingQueries.pl`.

### 7.3 Spreadsheet operations

Same pattern for `spreadsheet_operations/rows/*.row` (259 files) →
`dbif_config.spreadsheet_operation`. These define the operations analysts
invoke from DbIf:

```
:operation_name: ApplyMasks
:command_line: ApplyMasks.py <?bkgrnd_id?> <activity_id> <visual_review_instance_id> <notify>
:operation_type: background_process
:tags: ['export']
:can_chain:
```

Of the 259, **222 invoke a `.pl`** and 36 a `.py` — the operation layer is still
predominantly Perl. Synced by `SyncAllSpreadsheetOps` /
`FindMissingSpreadsheetOperations.pl`.

### 7.4 Practical consequence

**`git pull` does not update queries or operations.** You must run the sync
scripts. Conversely, editing a query through the UI diverges from git until
someone exports. Any confusion about "the query works on prod but not here" is
almost always this.

---

## 8. Background jobs

### 8.1 Redis worker queue [LIVE]

`WorkerNode.py` is the single live execution path:

1. `BRPOP` off `work_queue_{priority}` (0 = low, 1 = high) with a 5s timeout
2. Set status running via the FastAPI; fetch work item + subprocess invocation
3. Substitute `<?bkgrnd_id?>` into `command_line`
4. Wrap with `/usr/bin/time -v -o /tmp/<work_id>.time`
5. Run with stdin from the input file's path, capture stdout/stderr to temp
   files
6. Upload both back into Posda as files; set status finished/errored

Configured from `POSDA_INTERNAL_API_URL`, `POSDA_REDIS_HOST`,
`POSDA_WORKER_PRIORITY`, `POSDA_WORKER_NAME`, `POSDA_API_SYSTEM_TOKEN`.
Compose runs one low- and one high-priority worker; scale via `replicas`.

### 8.2 `Posda::BackgroundProcess` — not a dispatcher, but still a runtime library

Nothing invokes `Posda::BackgroundProcess` **as a job launcher** any more —
that role belongs entirely to the Redis queue. But the Perl scripts the workers
execute still `use` it internally for bookkeeping, and **191 scripts under
`Posda/bin/` do so**.

What it still provides to those scripts:

- creating the `background_subprocess` row and logging argv into
  `background_subprocess_params`
- `WriteToEmail` / report handles → files uploaded back into Posda
- activity status updates (`activity_task_status`)
- completion time, error recording

**Forking is disabled.** `Posda::BackgroundProcess::Daemonize` delegates to
`ForkAndExit`, whose fork block is commented out
(`Posda/include/Posda/BackgroundProcess.pm:181`):

```perl
sub ForkAndExit {
  my ($self) = @_;
  $self->{input_line_query} = undef;

  # shutdown STDOUT, 1;
  # if(fork){
  #   close STDIN;
  #   close STDOUT;
  #   exit;
  # }

  $self->{grandchild_pid} = $$;
  # ... set up queries, create Email report, continue in-process
```

It records its own PID as the "grandchild" and continues in the same process.
This is correct for the worker model: the worker needs the child to stay in the
foreground so it can wait on the exit code and capture stdout/stderr.

The Python mirror (`python/posda/background/process.py`) did the same thing and
says so explicitly: *"background scripts should no longer deamonize, so this is
removed; the method itself is kept for backwards compatability."*

**Implication for anyone touching these scripts:** `Daemonize()` /
`daemonize()` calls are load-bearing despite the name — they create the Email
report and rebind `stdout`. Don't delete them as dead code; they just no longer
fork.

---

## 9. DICOM handling

Homegrown, not a library binding.

- `Posda::Parser` (50 KB) + `Posda::Dataset` (108 KB) — from-scratch DICOM
  parser/writer, supporting implicit LE, explicit LE, and explicit BE
- `Posda::Try` — "is this file DICOM?" plus MD5 digest and length
- `PubDataDict.pm` (1.2 MB), `PvtDataDict.pm` (2.3 MB), `ElementNames.pm`
  (232 KB) — generated dictionaries
- `Posda/tpl/` — ~1 MB of DVTk-style IOD/module/element templates
- `Posda/c_source/` — 16 C programs for RT geometry: contour↔bitmap conversion,
  dose resampling, DVH binning, margin computation. Built with
  `make clean; make all; make install`

External binaries are shelled out to for specific jobs only:

| Tool | Uses (approx.) |
|---|---|
| ImageMagick `convert` / `identify` / `mogrify` | 120+ |
| `dciodvfy` / `dcentvfy` (dicom3tools) | 32 |
| `openslide` | 19 |
| `mail` | 33 |
| `storescu` | 3 |
| `dcmdump`, `dcm2niix`, `tesseract` | few |

Note: commit `01b33621` moved magicka's projection rendering from ImageMagick to
pydicom+numpy, so the ImageMagick count is trending down.

---

## 10. Dependencies

### Perl
`Modern::Perl`, `DBD::Pg`, `DBD::mysql`, `JSON`, `Data::UUID`, `Switch`,
`Text::Diff`, `Term::ReadKey`, `REST::Client`, `Net::LDAP`, `DateTime`,
`Method::Signatures::Simple`, `Redis`, `Text::CSV`(`::XS`), `Try::Tiny`,
`File::Slurp`, `Regexp::Common`, `Text::Markdown`, `Unicode::Map`.
CPAN-only (not in Debian repos): `xls2csv`, `HTTP::Request::StreamingUpload`.

`cpanfile` at the repo root is stale — it lists only the original 8 modules and
omits everything the Dockerfile actually installs.

### Python 3.14
`psycopg2`, `mysql-connector`, `pydicom`, `redis`, `requests`, `numpy`,
`pandas`, `nibabel`, `tifffile`, `imagecodecs`, `openslide-python`, `Pillow`,
`pyarrow`, `python-box`, `storable`, `xlsx2csv`, plus
`pydicom-background-editor` built from
`github.com/quasarj/pydicom-background-editor`.

`PYTHONPATH=/home/posda/posdatools/python` — the `posda` package
(`config`, `database`, `queries`, `activity`, `linkage`, `background`,
`subprocess`, `nifti`, `tifftags`, `anonymizeslide`) is the Python-side
counterpart to the Perl modules.

### Services
PostgreSQL 13, Redis, nginx, the FastAPI service at `/papi`.

### Native
dicom3tools (built from source in the Dockerfile), dcm2niix (built from source),
libgdcm-tools, ImageMagick, libopenslide, rclone.

---

## 11. Rough edges and gotchas

### Authentication is triple-implemented, two-thirds dead

`Posda::Auth::is_authorized` has an unconditional `return api_auth(...)` on its
third line. The LDAP and database branches below it are unreachable:

```perl
sub is_authorized {
  my ($username, $password) = @_;
  my $auth_type = Config('auth_type');

  return api_auth($username, $password);

  # # Use LDAP or Database, based on POSDA_AUTH_TYPE env var
  # if ($auth_type eq 'ldap') { ...
```

Real auth is a POST to the FastAPI `/auth/token` returning a bearer token.
`POSDA_AUTH_TYPE`, `POSDA_LDAP_*`, and `Posda::LDAPAuth` do nothing.
**Authorization** (as distinct from authentication) is still live and still
reads `auth.user_permissions` from Postgres via `Posda::Permissions`.

### Plaintext credentials in git

- `Config/databases.json` — MySQL password for `aries-nbia-1.ad.uams.edu`
- `Config/DbIf/Environment.json` — two more, for hosts `144.30.1.74` and
  `144.30.1.71`
- `config/common.env` — `POSDA_API_SYSTEM_TOKEN`, annotated "KEEP THIS SECRET!"

All present in history. Worth rotating anything still reachable.

### Weak session identifiers

`RandString` (both controllers, and `Dispatch::Http::App::Server`) is five
concatenated `int rand() * 1000` values — unseeded `rand`, roughly 15 bits of
real entropy. It is the sole authenticator for a logged-in session, carried in
the URL path.

### Dead config that looks live

- `SocketPool` in `Applications.json` (64665+) — ignored; see §4.3
- `posda_backlog` in `databases.json` — database no longer used
- `DicomReceiver` `StaticObjs` entry — still instantiated at startup, pipeline
  dead
- `POSDA_RECIEVER_PORT` (note the typo) and `POSDA_RECEIVE_DAEMON_PORT`

### Hardcoded developer paths

`TODO.md` tracks ~20 files with `bbennett` baked into absolute paths. Several
are *not* tests:

- `Posda/config/ae/srv` — `storage_root:/Users/bbennett/dicom_store`
- `Posda/bin/DB/ImportTgz.pl`, `ImportTgzOrZip.pl` — passes `"bbennett"` as the
  importing user
- `SetInitialExpertAndDebug("bbennett")` in `Posda/include/Posda/HttpApp/JavaScriptApp.pm`,
  `AppController/JavaScriptApp.pm`, and the `Application.pm` of PosdaCuration
  and TciaCuration

### Executable bits

The root `.gitignore` ignores `/bin/`, while `Posda/bin/` (655 files) is
tracked. Recent commits (`0cfc79c8`, `78970eb9`) fixed missing `+x` bits causing
production "Permission denied" — worth checking `git ls-files -s` mode `100755`
when adding a new script under `Posda/bin/`.

### `Dispatch::Select` fairness

`DispatchCurrentDefaults` drains at most `$MaxBackgrounds` (100) closures per
loop iteration, and a background item present at all forces the `select()`
timeout to 0. A tight background loop will spin the reactor.

---

## 12. Quick orientation map

| I want to… | Look at |
|---|---|
| Understand startup | `Posda/bin/AppController/AppController.pl`, `bin/shell_library.sh`, `posda/docker-entrypoint` |
| Change configuration | `posda.env`, `Config/SetEnv`, `Posda/include/Posda/Config.pm`, `Config/<App>/Environment.json` |
| Understand the event loop | `Posda/include/Dispatch/Select.pm` |
| Understand URL → code | `Dispatch::Http::App::Server::AppDispatch` and `Dispatch::Http::App::DispatchObj` in `Posda/include/Dispatch/Http.pm` |
| Work on the main UI | `DbIf/include/DbIf/Application.pm` (188 KB) |
| Add/edit a query | `queries/sql/*.sql` + `queries/import.py` — **then sync** |
| Add an analyst operation | `spreadsheet_operations/rows/*.row` + `SyncAllSpreadsheetOps` |
| Write a background script | `Posda/bin/Background*.pl` for Perl, `python/posda/background/process.py` for Python; see `docs/programming/Posda-BackgroundProcess.md` |
| Understand job execution | `WorkerNode.py` |
| Touch DICOM parsing | `Posda/include/Posda/{Try,Parser,Dataset}.pm` |
| Find the schema | `Posda/sql/posda_files.sql` |
