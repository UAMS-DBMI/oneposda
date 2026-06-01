# Posda FastAPI — Issues to fix

Findings from a review of `app/` on branch `posda-api-fixes`. Each item is
numbered so they can be referenced individually.

---

## Critical / security

### 1. Production bearer tokens committed to the repo — RESOLVED
`app/test-script.sh:5,10,15` contains `POSDA_API_SYSTEM_TOKEN` UUIDs for
ARIES and PROD. The real tokens were rotated when this was first spotted,
so the values in the file are no longer live. No further action required.

### 2. `eval()` on database content
`routes/send_to_public_status.py:57` calls `evil_eval(message)` on the
`error_message` column of `public_copy_status`. Anyone able to write that
column gets RCE. The helper module is even named `util/evil.py`. Parse the
structured data instead of `eval`-ing a repr.

### 3. SQL injection via request body — RESOLVED
`routes/edits.py:42-48` interpolated `scr.table_name` and `scr.column_name`
(from the JSON body) directly into the SQL string. The only Perl caller in
the main Posda codebase never sets those optional fields, so the model
fields were removed and the prior defaults (`dicom_edit_compare_disposition`
/ `current_disposition`) are hardcoded into the queries.

### 4. Auth bypass — user identity passed in URL path
`routes/pathology.py:109` (`PUT /set_edit/{pathid}/{good_status}/{user}`) and
the mapping endpoint at `:263` accept a `user` value in the path and persist
it as the actor. Any authenticated caller can impersonate anyone. Replace
with `current_user`.

### 5. Arbitrary directory listing
`routes/files.py:27 GET /listfiles` accepts a `path` query parameter and
walks the filesystem with the server's privileges. Constrain to an allowed
root or remove.

### 6. Importer router has no authentication
`routes/importer.py:15-17` does not include `dependencies=[logged_in_user]`.
`POST /import/file_in_place` (line 231) accepts an arbitrary `localpath` and
will `os.stat` / md5 / register any path the server can read. Add auth, and
constrain `localpath` to allowed roots.

### 7. Bearer tokens written to stdout
`routes/auth.py:55-56,80` prints both `API_SYSTEM_TOKEN` and the
caller-supplied bearer token to stdout on every request. Remove these prints
(or replace with `logging.debug` gated on a flag, never printing the value).

### 8. State-mutating GET endpoints
`routes/vrstatus.py:50,85`, `routes/send_to_public_status.py:217,230`, and
the `PUT`-shaped routes in `routes/pathology.py` that do INSERTs via paths.
GETs that update state are a CSRF risk and break REST/caching assumptions.
Convert to `POST`/`PUT`.

### 9. Shell injection surface in download path
`routes/download.py:61` calls `asyncio.create_subprocess_shell(cmd)` where
`cmd` contains `path` interpolated from the DB. Use
`create_subprocess_exec(cmd, *args)` so the path is never parsed by a shell.

---

## Real bugs

### 10. `return HTTPException(...)` instead of `raise`
`routes/iecs.py:26` and `routes/visualreviews.py:29` return the exception
object as a JSON body with HTTP 200 instead of raising it.

### 11. `RuntimeException` does not exist
`util/roi.py:12` raises `RuntimeException("contour is not in 3d space")`,
which is not a built-in. The contour-not-3D path raises `NameError`. Use
`RuntimeError` (or a specific exception).

### 12. `bytes_read` only retains the last chunk size
`util/digest.py:10` uses `bytes_read = len(chunk)` inside the read loop;
should be `+=`. The returned size is wrong for any multi-chunk file.

### 13. `aiofiles` file not awaited on close
`util/asynctar.py:25` calls `f.close()` synchronously on an async file
handle. Use `await f.close()`, or refactor to `async with`.

### 14. `HTTPException` raised without `status_code`
`routes/wadors.py:151,154` calls `HTTPException("not implemented yet")` and
`HTTPException()`. Both raise `TypeError` instead of returning an HTTP
error. Pass `status_code=501` (or similar).

### 15. `conv()` references a field the timepoint query never selects
`routes/wadors.py:282-303` is shared between `get_iec_metadata` (selects
`modality`) and `get_metadata2` (does not). Every call to `get_metadata2`
raises `KeyError: 'modality'`. Either add the column to the timepoint query
or make `conv` tolerate missing keys.

### 16. Path inserts use `db.fetch(...)` with no `RETURNING` — endpoints always 422 on success
In `routes/pathology.py`: `set_edit`, `remM`, `remL`, `remF`, `editM`,
`redact`, `cancelEdit`, `bulkMacro`, `bulkLabel`, `bulkMeta`,
`recordPathDBresponse` all do `record = await db.fetch(INSERT/UPDATE ...)`
then `if len(record) < 1: raise 422`. asyncpg returns `[]` for DML without
`RETURNING`, so the 422 fires on every successful write. Switch to
`db.execute(...)` and drop the length check, or add a `RETURNING` clause.

### 17. Unreachable error handling after `return`
`routes/pathology.py:511-536` (`insert_image_meta`) has `return await
db.fetch_one(...)` followed by `if record is None: raise ...`. The trailing
code is dead, and `record` is unbound. Move the check before the return.

### 18. `del json_body['stderr_file_id']` raises `KeyError` if absent
`routes/worker.py:60-61,85-86`. Use `.pop(..., None)`.

### 19. Duplicate function names shadow each other
Multiple files redefine handlers under the same Python name in the same
module: `routes/masking.py:43 & :69` (`get_work_for_masker`), `:294 & :322`
(`mark_accept`); `routes/work.py:14,29,51` (`get_work_status`). FastAPI
still registers the routes, but the OpenAPI operation IDs and any reverse
lookups collide. Rename each handler.

### 20. Untyped `request` parameter becomes a required query param
`routes/iecs.py:25` and `routes/visualreviews.py:28` declare
`async def f(request, **kwargs)`. FastAPI treats `request` as a required
query parameter, so the route 422s on every call. Annotate it as
`request: Request` or remove it.

### 21. Optional body assumed present
`routes/visualreviews.py:168` declares `params: VRFilterParameters = None`
then accesses `params.dicom_file_type`. A request with no body raises
`AttributeError`. Either make the body required or default to an instance.

### 22. Bare `except: pass`
`routes/nifti.py:128-129` in `get_for_visualreview` swallows everything and
implicitly returns `None`. Let exceptions propagate or convert to a specific
`HTTPException`.

### 23. `dict(fetch_one_result)` then `if item:` for 404
`routes/iecs.py:160`, `routes/nifti.py:60`. `db.fetch_one` returns `[]` on
miss; `dict([])` is `{}`, so the endpoint returns `{}` with HTTP 200 instead
of 404. Check for empty before constructing the dict.

### 24. Connection pool corruption via `set_type_codec`
`routes/dicom_roots.py:238-242` calls `set_type_codec('timestamp', ...)` on
a pooled connection. asyncpg keeps the codec on that connection after it's
returned, so future borrowers see string timestamps unexpectedly. Set the
codec at pool init (`init=`) or use a dedicated, non-pooled connection.

### 25. `results[0]` without empty check
`routes/series.py:129-130` reads `results[0]["study_instance_uid"]` in
`get_ohif_config` before checking whether any rows came back. Return 404 if
empty.

### 26. `/asynctar` test route is broken and dangerous
`routes/other.py:48` calls `asynctar.stream(...)` (no such symbol — module
exposes `stream_directory` / `stream_files`) with a hardcoded
`/home/quasar/projects/NBIA-TCIA` path. Delete the endpoint.

---

## Smaller correctness / hygiene

### 27. Sync redis client in async handlers
`util/redisqueue.py` and `routes/auth.py` use the blocking `redis` package
inside async functions, blocking the event loop on every login / token
decode. Switch to `redis.asyncio`.

### 28. Pydantic v1 idioms
`routes/other.py:54` calls `current_user.dict()` (deprecated). A few models
use bare `Optional[str]` without `= None`. Update to `.model_dump()` and
explicit defaults.

### 29. f-string interpolation of typed ints into SQL
`routes/series.py:305,330`, `routes/work.py:22,63`. Currently not
exploitable because FastAPI validates the type, but it's a footgun if a
parameter is ever loosened to a string. Use bind params.

### 30. Module-level `current_user = logged_in_user`
`routes/pathology.py:14` (and commented in `routes/nifti.py:18`). This
assigns the `Depends(...)` sentinel to a module global named `current_user`,
which is misleading. Delete the line.

### 31. `ROOT_MAP_CACHE` never invalidates
`routes/importer.py:25,202`. Changes to `file_storage_root` require an API
restart to take effect. Either drop the cache or add a TTL / refresh path.

### 32. `/listfiles` count check inside inner loop and over-indented
`routes/files.py:34-37`. The 5000-result guard fires only when the inner
loop runs, and the indentation is off. Move the check to the outer scope.
(Becomes moot once #5 is addressed.)

### 33. Request body consumed twice
`routes/worker.py:56-77` declares `error_files: ErrorFiles` (Pydantic) and
also `await request.json()`. Works today because Starlette caches the body,
but it's fragile. Read it once.

### 34. `asyncio.get_event_loop()` in startup hook
`main.py:114`. Deprecated since Python 3.10; use `asyncio.get_running_loop()`
(or move signal handling into the lifespan).

### 35. `@app.on_event("startup")` is deprecated
`main.py:107`. Migrate to the FastAPI `lifespan` context manager.

### 36. `check_db.py` uses `loop.run_until_complete`
`app/check_db.py:12`. Replace with `asyncio.run(run())`, and print the
exception so first-boot failures are diagnosable.

### 37. Dockerfile pins `python:3.10`
`Dockerfile:1`. Project guidance targets a much newer interpreter. Bump or
unpin (with a tested version).

### 38. `requirements.txt` has no version pins
`app/requirements.txt`. Every rebuild can pull a new major. Pin (and
consider switching to `uv` per project conventions).

### 39. Functional tests depend on prod data and skip auth
`tests/functional.py` hits `http://localhost/papi/v1` without a token,
against fixed prod IDs (docstring acknowledges this). They will 401 against
any real instance. Mock the DB layer or stand up fixtures.

### 40. `test_main.py` overrides the wrong dependency key
`app/test_main.py:17` does `app.dependency_overrides[Database] =
FakeDatabase`, but the routes use `db: Database = Depends()` (factory call
style). The override key needs to be the *callable* used in `Depends(...)`
(here `Database` itself works for class-based deps, but verify each route).
The commented-out `test_studies` suggests this never actually exercised the
overrides. Confirm and add coverage.

### 41. `Database.fetch_one` returns `[]` on miss while module-level `fetch_one` raises
`util/db.py:41-42` vs `:62-72`. Two different "not found" contracts in the
same module. Several callers rely on the empty-list version (`if len(...)
< 1`). Pick one and apply consistently.

### 42. `pos = iter(range(1, 10))` caps `searchRoots` at 9 conditions
`routes/dicom_roots.py:47`. Future fields silently raise `StopIteration`.
Use `itertools.count(1)`.

### 43. `print(query, values)` leaks queries to logs
`routes/dicom_roots.py:103`. Remove or move to `logging.debug`.

### 44. `LIKE` queries on user input without escaping wildcards
`routes/dicom_roots.py:50-83`. `%` and `_` in user input behave as
wildcards. If exact match is intended, use `=`; if substring, escape.

### 45. Activity ID is ignored in `routes/activities.py` timeline endpoints
`get_timeline_entry`, `_input`, `_output`, `_errors` all key only on
`timeline_id`. Either drop `activity_id` from the path or enforce that the
timeline belongs to it.
