// Database access: a thin wrapper over Bun's built-in Postgres client
// mirroring the Python implementation's Database class. Queries return
// rows as plain objects whose key order matches the select list
// (asyncpg Records rendered by FastAPI preserve column order; JS
// objects preserve insertion order, and duplicate columns collapse
// first-position/last-value exactly like Python's dict()).

import { SQL } from "bun";
import { convertRow, type Convs } from "./pgconvert";

export type Row = Record<string, unknown>;

/** One transaction handle (the object Bun passes to sql.begin). */
export type Tx = SQL;

export class Db {
  private constructor(public readonly sql: SQL) {}

  /**
   * Connect to the given database. Host, port, user and password come
   * from the standard PG* environment variables, like asyncpg/libpq.
   * TimeZone is pinned to UTC so timestamptz text renders with +00.
   */
  static async connect(database: string): Promise<Db> {
    const sql = new SQL({
      hostname: process.env.PGHOST || "localhost",
      port: Number(process.env.PGPORT || 5432),
      username: process.env.PGUSER || "postgres",
      password: process.env.PGPASSWORD,
      database,
      max: 10,
      connection: { TimeZone: "UTC" },
    });
    await sql`select 1`;
    return new Db(sql);
  }

  async close(): Promise<void> {
    await this.sql.end();
  }

  /** Run a query and return all rows. */
  async fetch<T extends object = Row>(
    text: string,
    params: unknown[] = [],
    convs?: Convs,
  ): Promise<T[]> {
    return fetchOn<T>(this.sql, text, params, convs);
  }

  /** Run a query and return the first row, or undefined when empty. */
  async fetchOne<T extends object = Row>(
    text: string,
    params: unknown[] = [],
    convs?: Convs,
  ): Promise<T | undefined> {
    const rows = await this.fetch<T>(text, params, convs);
    return rows[0];
  }

  /** Run a statement without returning rows. */
  async exec(text: string, params: unknown[] = []): Promise<void> {
    await this.sql.unsafe(text, params as any[]);
  }

  /** Run fn inside a transaction, committing if it does not throw. */
  async tx<T>(fn: (tx: Tx) => Promise<T>): Promise<T> {
    return (await this.sql.begin(fn)) as T;
  }
}

/** fetch on an open transaction (or any SQL handle). */
export async function fetchOn<T extends object = Row>(
  sql: SQL,
  text: string,
  params: unknown[] = [],
  convs?: Convs,
): Promise<T[]> {
  const rows = (await sql.unsafe(text, params as any[])) as unknown as T[];
  if (convs) for (const row of rows) convertRow(row as Record<string, unknown>, convs);
  return rows;
}

/** fetchOne on an open transaction. */
export async function fetchOneOn<T extends object = Row>(
  sql: SQL,
  text: string,
  params: unknown[] = [],
  convs?: Convs,
): Promise<T | undefined> {
  const rows = await fetchOn<T>(sql, text, params, convs);
  return rows[0];
}

interface PgError {
  errno?: string;
}

function sqlState(err: unknown): string {
  return (err as PgError)?.errno ?? "";
}

/** Postgres unique_violation. */
export function isUniqueViolation(err: unknown): boolean {
  return sqlState(err) === "23505";
}

/** Postgres foreign_key_violation. */
export function isForeignKeyViolation(err: unknown): boolean {
  return sqlState(err) === "23503";
}

/** Postgres invalid_text_representation (e.g. bad enum input). */
export function isInvalidTextRepresentation(err: unknown): boolean {
  return sqlState(err) === "22P02";
}
