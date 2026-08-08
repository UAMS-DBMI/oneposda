package db

import (
	"fmt"
	"math"
	"math/big"
	"reflect"
	"time"

	"github.com/jackc/pgx/v5/pgtype"
)

// jsonValue converts a pgx-decoded value into something that serializes
// to JSON the way FastAPI serializes the corresponding asyncpg value:
//
//	date        -> "2006-01-02"
//	timestamp   -> "2006-01-02T15:04:05[.ffffff]"       (naive isoformat)
//	timestamptz -> "2006-01-02T15:04:05[.ffffff]+00:00" (aware isoformat)
//	time        -> "15:04:05[.ffffff]"
//	interval    -> total seconds as a float (timedelta.total_seconds())
//	numeric     -> int when exponent >= 0, else float (pydantic decimal_encoder)
//	uuid        -> canonical string
//	bytea       -> string
func jsonValue(oid uint32, v any) any {
	if v == nil {
		return nil
	}
	switch oid {
	case pgtype.DateOID:
		if t, ok := v.(time.Time); ok {
			return t.Format("2006-01-02")
		}
	case pgtype.TimestampOID:
		if t, ok := v.(time.Time); ok {
			return pyDateTime(t, false)
		}
	case pgtype.TimestamptzOID:
		if t, ok := v.(time.Time); ok {
			return pyDateTime(t, true)
		}
	case pgtype.TimeOID:
		if t, ok := v.(pgtype.Time); ok {
			return pyTime(t)
		}
	case pgtype.IntervalOID:
		if iv, ok := v.(pgtype.Interval); ok {
			return intervalSeconds(iv)
		}
	case pgtype.NumericOID:
		if n, ok := v.(pgtype.Numeric); ok {
			return numericValue(n)
		}
	case pgtype.UUIDOID:
		if u, ok := v.([16]byte); ok {
			return formatUUID(u)
		}
	case pgtype.ByteaOID:
		if b, ok := v.([]byte); ok {
			return string(b)
		}
	}
	return anyValue(v)
}

// anyValue handles values with no OID context (array elements, values
// of composite types) plus the pass-through primitives.
func anyValue(v any) any {
	switch t := v.(type) {
	case nil, bool, string, int16, int32, int64, float32, float64:
		return v
	case time.Time:
		// No OID context: render date-only values as dates.
		if t.Hour() == 0 && t.Minute() == 0 && t.Second() == 0 && t.Nanosecond() == 0 {
			return t.Format("2006-01-02")
		}
		return pyDateTime(t, false)
	case pgtype.Time:
		return pyTime(t)
	case pgtype.Interval:
		return intervalSeconds(t)
	case pgtype.Numeric:
		return numericValue(t)
	case [16]byte:
		return formatUUID(t)
	case []byte:
		return string(t)
	}

	// Recurse into slices (array columns decode as []any or typed slices).
	rv := reflect.ValueOf(v)
	if rv.Kind() == reflect.Slice {
		out := make([]any, rv.Len())
		for i := range rv.Len() {
			out[i] = anyValue(rv.Index(i).Interface())
		}
		return out
	}
	return v
}

// pyDateTime formats t the way Python's datetime.isoformat() does:
// microseconds only when nonzero, and a +hh:mm offset only for aware
// (timestamptz) values.
func pyDateTime(t time.Time, withOffset bool) string {
	s := t.Format("2006-01-02T15:04:05")
	if us := t.Nanosecond() / 1000; us != 0 {
		s += fmt.Sprintf(".%06d", us)
	}
	if withOffset {
		s += t.Format("-07:00")
	}
	return s
}

func pyTime(t pgtype.Time) string {
	if !t.Valid {
		return ""
	}
	us := t.Microseconds
	h := us / 3_600_000_000
	us -= h * 3_600_000_000
	m := us / 60_000_000
	us -= m * 60_000_000
	sec := us / 1_000_000
	us -= sec * 1_000_000
	s := fmt.Sprintf("%02d:%02d:%02d", h, m, sec)
	if us != 0 {
		s += fmt.Sprintf(".%06d", us)
	}
	return s
}

// intervalSeconds mirrors asyncpg's interval->timedelta conversion
// followed by timedelta.total_seconds().
func intervalSeconds(iv pgtype.Interval) any {
	if !iv.Valid {
		return nil
	}
	days := float64(iv.Months)*30 + float64(iv.Days)
	return days*86400 + float64(iv.Microseconds)/1e6
}

// numericValue mirrors pydantic's decimal_encoder: integral decimals
// become ints, everything else becomes a float.
func numericValue(n pgtype.Numeric) any {
	if !n.Valid || n.NaN {
		return nil
	}
	if n.Exp >= 0 {
		i := new(big.Int).Set(n.Int)
		if n.Exp > 0 {
			i.Mul(i, new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(n.Exp)), nil))
		}
		if i.IsInt64() {
			return i.Int64()
		}
		f, _ := new(big.Float).SetInt(i).Float64()
		return f
	}
	f, err := n.Float64Value()
	if err != nil || !f.Valid {
		return nil
	}
	if math.IsNaN(f.Float64) || math.IsInf(f.Float64, 0) {
		return nil
	}
	return f.Float64
}

func formatUUID(u [16]byte) string {
	return fmt.Sprintf("%x-%x-%x-%x-%x", u[0:4], u[4:6], u[6:8], u[8:10], u[10:16])
}
