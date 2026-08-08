package db

import (
	"bytes"
	"encoding/json"
)

// Row is a single result row. It preserves column order when serialized
// to JSON, matching the behavior of asyncpg Records rendered by FastAPI.
type Row struct {
	Columns []string
	values  []any
}

// NewRow builds an empty row for handlers that construct responses.
func NewRow() Row {
	return Row{}
}

// Get returns the value of the named column (nil if not present).
func (r Row) Get(col string) any {
	for i, c := range r.Columns {
		if c == col {
			return r.values[i]
		}
	}
	return nil
}

// GetInt returns the named column as int64. Returns 0 for nil/missing.
func (r Row) GetInt(col string) int64 {
	switch v := r.Get(col).(type) {
	case int64:
		return v
	case int32:
		return int64(v)
	case int16:
		return int64(v)
	case int:
		return int64(v)
	case float64:
		return int64(v)
	}
	return 0
}

// GetString returns the named column as a string ("" for nil/missing).
func (r Row) GetString(col string) string {
	if s, ok := r.Get(col).(string); ok {
		return s
	}
	return ""
}

// GetBool returns the named column as a bool (false for nil/missing).
func (r Row) GetBool(col string) bool {
	if b, ok := r.Get(col).(bool); ok {
		return b
	}
	return false
}

// Set replaces the value of col, or appends a new column if not present.
func (r *Row) Set(col string, val any) {
	for i, c := range r.Columns {
		if c == col {
			r.values[i] = val
			return
		}
	}
	r.Columns = append(r.Columns, col)
	r.values = append(r.values, val)
}

// Delete removes the named column if present.
func (r *Row) Delete(col string) {
	for i, c := range r.Columns {
		if c == col {
			r.Columns = append(r.Columns[:i], r.Columns[i+1:]...)
			r.values = append(r.values[:i], r.values[i+1:]...)
			return
		}
	}
}

// Values returns the row values in column order.
func (r Row) Values() []any {
	return r.values
}

// MarshalJSON serializes the row as an object, preserving column order.
// Duplicate column names (possible with "select *" over joins) collapse
// the same way Python's dict() does: first position, last value.
func (r Row) MarshalJSON() ([]byte, error) {
	// resolve duplicates: dict() keeps first-insertion position, last value
	order := make([]int, 0, len(r.Columns))
	seen := make(map[string]int, len(r.Columns))
	for i, c := range r.Columns {
		if prev, dup := seen[c]; dup {
			r.values[prev] = r.values[i]
			continue
		}
		seen[c] = i
		order = append(order, i)
	}

	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	buf.WriteByte('{')
	for n, i := range order {
		if n > 0 {
			buf.WriteByte(',')
		}
		if err := enc.Encode(r.Columns[i]); err != nil {
			return nil, err
		}
		trimNewline(&buf)
		buf.WriteByte(':')
		if err := enc.Encode(r.values[i]); err != nil {
			return nil, err
		}
		trimNewline(&buf)
	}
	buf.WriteByte('}')
	return buf.Bytes(), nil
}

func trimNewline(buf *bytes.Buffer) {
	b := buf.Bytes()
	if len(b) > 0 && b[len(b)-1] == '\n' {
		buf.Truncate(len(b) - 1)
	}
}
