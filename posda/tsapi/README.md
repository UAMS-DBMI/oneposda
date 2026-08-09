# Posda API (TypeScript / Bun)

A TypeScript rewrite of the Posda API, executed directly by [Bun](https://bun.sh)
with no build step and no runtime dependencies beyond Bun itself. It is a
port of the Go implementation in `posda/goapi` (itself a verified port of
the original Python/FastAPI implementation in `posda/fastapi`): routes,
SQL queries, auth, and response shapes match, including the intentional
differences from Python documented in the Go README.

## Why Bun / TypeScript

- Bun executes the TypeScript sources directly (`bun src/main.ts`) —
  no transpile or bundle step.
- Postgres (`Bun.sql`), Redis (`Bun.redis`), HTTP routing (`Bun.serve`)
  and gzip are all built in, so `package.json` has zero runtime
  dependencies (`@types/bun` is dev-only).
- Endpoint responses are typed: every query has an explicit column list
  and a TypeScript interface describing the row shape, both deduced
  from the database schema (`information_schema` / `\gdesc`). The
  `select *` queries of the Python original were expanded to explicit
  columns.

## Layout

    src/main.ts        entrypoint
    src/config.ts      environment configuration (same variables as Python/Go)
    src/db.ts          Bun.sql wrapper returning asyncpg-shaped rows
    src/pgconvert.ts   per-column type conversions (see below)
    src/pyjson.ts      JSON serializer with Python float conventions
    src/auth.ts        login tokens (redis db 1), Perl-compatible password hashes
    src/password.ts    salt,sha256-base64 password hashing (Passwords.pm)
    src/httpx.ts       FastAPI-style error responses ({"detail": ...})
    src/server.ts      route table, auth middleware, gzip policy
    src/routes/        one file per Python route module
    src/archive.ts     streaming zip and tar.gz downloads
    src/dicom.ts       slice-ordering + ROI contour transform math
    src/evilparse.ts   safe replacement for evil.py's eval() of error messages
    tests/             bun test suite

## Running

Configuration comes from the same environment variables as the Python
and Go implementations: `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` (libpq
conventions; the server always connects to the `posda_files` database),
`API_PORT` (default 8087), `POSDA_REDIS_HOST`, `POSDA_API_SYSTEM_TOKEN`,
`POSDA_API_URL`, `FILE_STORAGE_PATH`, `TEMP_STORAGE_PATH`,
`FILE_STORAGE_ROOT`, and `DUMP_SCRIPT`.

    bun install     # dev types only; nothing needed at runtime
    make run        # bun src/main.ts
    make test       # bun test
    make typecheck  # bunx tsc --noEmit
    make image      # build the docker image

## Serialization parity

JSON responses reproduce what FastAPI produces from asyncpg records
(the same conventions the Go port implements — see goapi/README.md):
column order is preserved, dates/timestamps use Python isoformat
(timestamptz as UTC "+00:00"), intervals become total seconds as a
float, `numeric` becomes int or float depending on display scale
("0.000000" -> 0.0), json/jsonb columns stay raw text, and floats print
Python-style ("0.0", not "0").

Bun's Postgres client does not expose result column type OIDs and
decodes timestamps into millisecond-precision `Date`s, so the strategy
differs from pgx/asyncpg:

- timestamp/timestamptz/json/jsonb columns are selected as `col::text`
  (connections pin `TimeZone=UTC` so timestamptz text is always +00),
- each query declares the columns needing conversion (numeric, float,
  int8, date, interval, ...) in a small `Convs` map next to its row
  interface (`src/pgconvert.ts` documents every rule),
- float-typed values are wrapped in `PyFloat` so the serializer in
  `src/pyjson.ts` can keep the trailing ".0"; `PyFloat` has `valueOf()`
  so handler arithmetic still works.

Verified by diffing 140 endpoints (plus the write paths) between this
implementation and the Go one on the same dev database: byte-identical
except for values derived from `now()` and three endpoints where the
Go port serializes hand-built maps with sorted keys — this port keeps
Python's dict insertion order there, matching the original more
closely.

## Differences from the Go port

- JSON objects built in handler code keep Python's insertion order
  (`/v1/other/query/...`, `/v1/series/.../ohif` metadata); Go emits
  those with sorted keys. The WADO-RS metadata maps keep Go's sorted
  order, since that is what the Go port shipped.
- The 422 for `/v1/masking/{iec}/parameters` with several missing
  required fields names the first missing field deterministically
  (LR, PA, IS, width, height, depth); Go picks one at random (map
  iteration order).
- Zip downloads are STORED archives like zipstream, but the exact
  archive bytes (header metadata, no data descriptors) differ from
  both the Python and Go implementations; the extracted contents are
  identical.
- `/v1/files/listfiles` walks directories in sorted order (like Go's
  WalkDir); Python's os.walk order is filesystem-dependent.

All the intentional behavior differences from the Python implementation
listed in goapi/README.md apply here as well (fixed pydantic-v2 500s,
SQL-injection fix in /v1/edits/state, simple-string validation errors,
explicit 500 for /v1/other/asynctar, evilparse instead of eval, no
OpenAPI docs endpoints).
