// Package db wraps a pgx connection pool with helpers that mirror the
// Python implementation's Database class: queries return rows as
// column-ordered maps ready for JSON serialization.
package db

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

type DB struct {
	Pool *pgxpool.Pool
}

// Connect creates a pool against the given database. Host, port, user
// and password are taken from the standard PG* environment variables,
// exactly like asyncpg/libpq.
func Connect(ctx context.Context, database string) (*DB, error) {
	cfg, err := pgxpool.ParseConfig(fmt.Sprintf("database=%s", database))
	if err != nil {
		return nil, fmt.Errorf("parsing database config: %w", err)
	}
	// json/jsonb columns are returned as raw text, matching asyncpg
	// (which hands JSON columns to the application as strings).
	// numeric columns also come back as text: pgx's binary codec drops
	// the display scale, which decides whether a value serializes as an
	// int or a float (Decimal('0.000000') is a float, Decimal('0') an
	// int — see numericStringValue).
	cfg.AfterConnect = func(ctx context.Context, conn *pgx.Conn) error {
		tm := conn.TypeMap()
		tm.RegisterType(&pgtype.Type{Name: "json", OID: pgtype.JSONOID, Codec: pgtype.TextCodec{}})
		tm.RegisterType(&pgtype.Type{Name: "jsonb", OID: pgtype.JSONBOID, Codec: pgtype.TextCodec{}})
		tm.RegisterType(&pgtype.Type{Name: "numeric", OID: pgtype.NumericOID, Codec: pgtype.TextCodec{}})
		return nil
	}
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("creating connection pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("pinging database: %w", err)
	}
	return &DB{Pool: pool}, nil
}

func (d *DB) Close() {
	d.Pool.Close()
}

// Fetch runs a query and returns all rows.
func (d *DB) Fetch(ctx context.Context, sql string, args ...any) ([]Row, error) {
	rows, err := d.Pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, err
	}
	return collectRows(rows)
}

// FetchOne runs a query and returns the first row. The second return
// value is false if the query returned no rows.
func (d *DB) FetchOne(ctx context.Context, sql string, args ...any) (Row, bool, error) {
	all, err := d.Fetch(ctx, sql, args...)
	if err != nil {
		return Row{}, false, err
	}
	if len(all) == 0 {
		return Row{}, false, nil
	}
	return all[0], true, nil
}

// Exec runs a statement without returning rows.
func (d *DB) Exec(ctx context.Context, sql string, args ...any) error {
	_, err := d.Pool.Exec(ctx, sql, args...)
	return err
}

// Tx runs fn inside a transaction, committing if it returns nil.
func (d *DB) Tx(ctx context.Context, fn func(tx pgx.Tx) error) error {
	tx, err := d.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// FetchTx is Fetch but on an open transaction.
func FetchTx(ctx context.Context, tx pgx.Tx, sql string, args ...any) ([]Row, error) {
	rows, err := tx.Query(ctx, sql, args...)
	if err != nil {
		return nil, err
	}
	return collectRows(rows)
}

// FetchOneTx is FetchOne but on an open transaction.
func FetchOneTx(ctx context.Context, tx pgx.Tx, sql string, args ...any) (Row, bool, error) {
	all, err := FetchTx(ctx, tx, sql, args...)
	if err != nil {
		return Row{}, false, err
	}
	if len(all) == 0 {
		return Row{}, false, nil
	}
	return all[0], true, nil
}

func collectRows(rows pgx.Rows) ([]Row, error) {
	defer rows.Close()

	fields := rows.FieldDescriptions()
	columns := make([]string, len(fields))
	oids := make([]uint32, len(fields))
	for i, fd := range fields {
		columns[i] = fd.Name
		oids[i] = fd.DataTypeOID
	}

	// Initialized non-nil so empty results serialize as [] rather than null.
	out := []Row{}
	for rows.Next() {
		vals, err := rows.Values()
		if err != nil {
			return nil, err
		}
		conv := make([]any, len(vals))
		for i, v := range vals {
			conv[i] = jsonValue(oids[i], v)
		}
		out = append(out, Row{Columns: columns, values: conv})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
