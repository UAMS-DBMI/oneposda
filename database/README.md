# Database seed

`all.sql` is what a fresh Posda install runs on an empty PostgreSQL server
(`docker-compose.yaml` mounts it into `docker-entrypoint-initdb.d`). It is a
**generated file**: do not edit it, rebuild it.

```sh
export PGHOST=localhost PGPORT=5433 PGUSER=postgres PGPASSWORD=…   # a dev database
./build-all-sql            # rewrite all.sql
./build-all-sql --check    # exit 1 if all.sql no longer matches the database
git diff --stat all.sql    # review what changed before committing
```

The script needs only `pg_dump` and `psql`, at the same major version as the
server. See the docstring at the top of `build-all-sql` for what each database
contributes; in short:

| What                                      | Where it comes from                              |
|-------------------------------------------|--------------------------------------------------|
| DDL for every database                    | `pg_dump --schema-only`, allowlisted schemas only |
| DbIf configuration, migration ledger      | `pg_dump --data-only` of `dbif_config`, `db_version` |
| Lookup tables that a migration seeded     | `pg_dump --data-only` of those tables             |
| DICOM dictionary, `element_seen`          | `pg_dump --data-only`                             |
| Private tag knowledge base                | `posdatools/Posda/sql/private_tag_kb_data.sql` (curated in git) |
| `auth` content, daemon control rows       | `seed/*.sql`, hand-written                        |
| DbIf query library                        | compiled from `posdatools/queries/sql`            |

Two things are deliberate and worth knowing:

* **The `auth` schema is never dumped.** A fresh install gets the `system`
  and `admin` accounts from `seed/posda_files_auth.sql` and nothing else. Add
  new applications and permissions there.
* **The migration ledger ships with the dump.** A database created from
  `all.sql` already records every migration the source database had applied,
  so `migrations/migrate status` reports nothing pending. That also means a
  migration that *seeds data* must have its tables listed in `build-all-sql`,
  or a fresh install will have the ledger row but not the rows.

`reset.sh` drops every Posda database on the server your PG\* variables point
at; use it to test a rebuilt `all.sql` from scratch.
