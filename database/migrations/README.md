# Database migrations

Forward-only migrations for the Posda databases, run by `./migrate`.

Each subdirectory is one target, named after the database it migrates
(`posda_files`, `posda_auth`, `posda_phi_simple`). Migrations run in sorted
filename order, and each database records what it has applied in its own
`db_version.migration` table — so a database can always be asked directly what
it is missing, rather than inferring it from a git diff.

## Usage

Connection settings come from the standard PG\* environment variables, the same
ones `psql` reads:

```sh
export PGHOST=localhost PGPORT=5433 PGUSER=postgres PGPASSWORD=…

./migrate status              # what is applied, pending, or divergent
./migrate up                  # apply everything pending
./migrate up posda_files      # just one target
./migrate up --dry-run        # report, change nothing
./migrate verify              # exit non-zero if anything is pending (for CI)
```

Deployments that prefix their database names take `--prefix`:

```sh
./migrate --prefix N_ status   # targets N_posda_files, N_posda_auth, …
```

## Adding a migration

Name it with a date prefix and drop it in the target directory:

```
posda_files/20260812_add_widget_table.sql
```

That's the whole process — there is no index file to update. Date prefixes sort
after the legacy `0001`–`0050` numbers and don't collide when two branches add a
migration in the same week, the way sequential numbers do.

Write migrations to run inside a transaction: `./migrate` wraps each one in
`--single-transaction`, so a failure rolls back both the schema change and its
ledger row, leaving nothing half-applied. Don't put `BEGIN`/`COMMIT` in the file
itself.

Never edit a migration that has been applied. `./migrate` hashes each file and
reports one that changed since it ran, because that means databases that
already applied it and databases that haven't will end up different. Add a new
migration instead.

### manual/

Files under `<target>/manual/` are never applied automatically. That's for
teardown scripts and seed data — things that live with the migrations but must
be run deliberately, by hand.

## Onboarding an existing database

A database that predates this ledger has the schema but no record of it, so its
migrations must be *stamped*, not run:

```sh
./migrate baseline posda_files --through 0043_add_uid_root_to_submissions.sql
./migrate status                 # confirm the remainder is what you expect
./migrate up
```

Pick the cutoff by checking what the database actually contains — do not guess.
Stamping too far silently skips migrations that were never applied.

A database created from `database/all.sql` needs no baseline: `all.sql` is
built by `database/build-all-sql` from a database that has every migration
applied, and it carries that database's `db_version.migration` ledger along
with the schema. `./migrate status` on a fresh install reports nothing pending.

## Why this and not a migration tool

The requirements are modest — several databases, forward-only, no rollback — and
the constraint that mattered was dependencies. `./migrate` is one file of
standard-library Python that shells out to `psql`.

Using `psql` rather than a database driver is deliberate: it keeps the
dependency list empty, and it means `COPY FROM STDIN` and backslash
meta-commands behave exactly as they do when a human runs the file by hand. An
earlier attempt at this used psycopg2 and stalled on precisely that.

## Tests

```sh
uv run --with pytest python -m pytest tests/
```

The tests that need a server are skipped unless one is reachable; they create
and drop their own scratch databases and never touch a real one.
