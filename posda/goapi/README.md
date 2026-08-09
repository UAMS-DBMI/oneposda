# Posda API (Go)

A Go rewrite of the Posda API previously implemented with Python/FastAPI
in `posda/fastapi`. Routes, SQL queries, auth, and response shapes match
the Python implementation; see "Intentional differences" below for the
places where they deliberately diverge.

## Why Go

- The API is almost entirely "run a SQL query, return the rows as
  JSON", frequently with `select *` whose shape is only known from the
  database. Dynamic row-to-JSON is natural with pgx; a type-first Rust
  ORM would fight this the whole way.
- Streaming zip / tar.gz downloads and gzip response compression are
  covered by the Go standard library.
- Single static binary, small container image, fast builds.

## Layout

    cmd/posda-api/        entrypoint
    internal/config/      environment configuration (same variables as Python)
    internal/db/          pgx pool + row-to-JSON conventions matching asyncpg/FastAPI
    internal/auth/        login tokens (redis db 1), Perl-compatible password hashes
    internal/httpx/       FastAPI-style error responses ({"detail": ...})
    internal/server/      handler assembly + gzip middleware
    internal/routes/      one file per Python route module
    internal/archive/     streaming zip and tar.gz downloads
    internal/dicom/       slice-ordering + ROI contour transform math
    internal/evilparse/   safe replacement for evil.py's eval() of error messages

## Running

Configuration comes from the same environment variables as the Python
implementation: `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` (libpq
conventions; the server always connects to the `posda_files` database),
`API_PORT` (default 8087), `POSDA_REDIS_HOST`, `POSDA_API_SYSTEM_TOKEN`,
`POSDA_API_URL`, `FILE_STORAGE_PATH`, `TEMP_STORAGE_PATH`,
`FILE_STORAGE_ROOT`. `DUMP_SCRIPT` (new, optional) overrides the
location of the DICOM dump script, defaulting to the historical
`/fastapi/dump_dicom.sh`.

    make build      # build ./posda-api
    make test       # run the test suite
    make image      # build the docker image

## Serialization parity

JSON responses reproduce what FastAPI produces from asyncpg records:

- column order is preserved in JSON objects; duplicate columns collapse
  like Python `dict()` (first position, last value)
- `date` -> `"2007-02-28"`, `timestamp` -> `"2007-02-28T11:12:59"` (no
  offset), `timestamptz` -> UTC with `"+00:00"`, `time` -> `"11:12:59"`
- `interval` -> total seconds as a float
- `numeric` -> int when the value has no fractional digits, float
  otherwise (including `0.000000` -> `0.0`)
- `json`/`jsonb` columns -> their raw text, not a nested object
- floats print Python-style (`0.0`, not `0`)
- endpoints whose Python versions used pydantic response models render
  datetimes/durations in pydantic v2 style (`Z` suffix, ISO-8601
  durations) where the live API demonstrated it

Verified by diffing ~80 endpoints against the running Python API on the
same dev database.

## Intentional differences from the Python implementation

Bug-for-bug compatibility was kept where clients might depend on it
(e.g. the pathology PUT endpoints still answer 422 after a successful
write, because their INSERTs return no rows and the Python code treated
that as an error). The following differences are deliberate:

- **Endpoints broken by pydantic v2 now work.** Under Python 3.14 +
  pydantic v2, every endpoint with a `response_model` fed by raw
  asyncpg records 500s (`/v1/collections/`, `/v1/studies/{uid}/series`,
  ...). The Go versions return the data those endpoints were written to
  return.
- `/v1/edits/state` only accepts plain SQL identifiers for
  `table_name`/`column_name`; the Python version interpolated them into
  SQL verbatim (SQL injection).
- Validation errors (bad path/query/body parameters) return a simple
  `{"detail": "<message>"}` string rather than pydantic's error array.
  Status codes match (422).
- `/v1/iecs/{iec}/frames?include_frames=false` returns
  `{"volumetric": ...}`; the Python version 500s on response-model
  validation.
- WADO-RS timepoint metadata omits a modality value instead of raising
  the Python `KeyError` 500 (the query never selected `modality`).
- Masking/visual-review filter endpoints treat a missing request body
  as "no filters" instead of the Python `AttributeError` 500.
- The DICOM dump endpoint falls back to latin-1 when output is not
  UTF-8, instead of chardet's guess.
- `/v1/other/asynctar` always 500s (it always did: it calls a function
  that does not exist) — implemented as an explicit 500.
- The OpenAPI document is generated at build time rather than derived
  from the running app (see below), so it describes response bodies
  that FastAPI left undocumented, and `/redoc` does not exist.
- The eval() of stored error messages in
  `/v1/send_to_public_status/report/{id}` is replaced by a real parser
  (`internal/evilparse`); it produces the same output for well-formed
  messages without executing anything.

## API documentation

The API serves its own OpenAPI document and a Swagger UI:

    /openapi.json    the OpenAPI 3.1 document
    /docs            Swagger UI (assets vendored, no CDN needed)

Both are public, as they were in FastAPI, and both work under the
`/papi` prefix as well.

The document is *not* generated from this code. It is produced from the
route annotations in the TypeScript port — which carries an explicit
response interface per query — by `posda/tsapi/scripts/genopenapi.ts`,
which writes an identical copy into `internal/docs/openapi.json` for
`go:embed` to pick up. Regenerate both with:

    cd ../tsapi && make openapi

`internal/docs/docs_test.go` checks the embedded copy parses and is not
truncated; `cd ../tsapi && make openapi-check` fails if it is stale.
