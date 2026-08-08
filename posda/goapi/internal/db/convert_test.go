package db

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgtype"
)

func TestPyDateTime(t *testing.T) {
	cases := []struct {
		t          time.Time
		withOffset bool
		want       string
	}{
		{time.Date(2023, 1, 2, 3, 4, 5, 0, time.UTC), false, "2023-01-02T03:04:05"},
		{time.Date(2023, 1, 2, 3, 4, 5, 626486000, time.UTC), false, "2023-01-02T03:04:05.626486"},
		{time.Date(2023, 1, 2, 3, 4, 5, 0, time.UTC), true, "2023-01-02T03:04:05+00:00"},
		{time.Date(2023, 1, 2, 3, 4, 5, 500000000, time.UTC), true, "2023-01-02T03:04:05.500000+00:00"},
	}
	for _, c := range cases {
		if got := pyDateTime(c.t, c.withOffset); got != c.want {
			t.Errorf("pyDateTime(%v, %v) = %q, want %q", c.t, c.withOffset, got, c.want)
		}
	}
}

func TestPyTime(t *testing.T) {
	mk := func(us int64) pgtype.Time { return pgtype.Time{Microseconds: us, Valid: true} }
	if got := pyTime(mk(11*3600e6 + 12*60e6 + 59e6)); got != "11:12:59" {
		t.Errorf("got %q", got)
	}
	if got := pyTime(mk(1e6 + 250000)); got != "00:00:01.250000" {
		t.Errorf("got %q", got)
	}
}

func TestNumericStringValue(t *testing.T) {
	cases := []struct {
		in   string
		want string // JSON form
	}{
		{"0", "0"},
		{"42", "42"},
		{"0.000000", "0.0"},
		{"1.5", "1.5"},
		{"32.486489", "32.486489"},
		{"-7", "-7"},
	}
	for _, c := range cases {
		got, err := json.Marshal(numericStringValue(c.in))
		if err != nil {
			t.Fatal(err)
		}
		if string(got) != c.want {
			t.Errorf("numericStringValue(%q) marshals to %s, want %s", c.in, got, c.want)
		}
	}
}

func TestPyFloatMarshal(t *testing.T) {
	cases := []struct {
		in   float64
		want string
	}{
		{0, "0.0"},
		{1, "1.0"},
		{-3, "-3.0"},
		{0.5, "0.5"},
		{411725.809976, "411725.809976"},
		{1e21, "1e+21"},
	}
	for _, c := range cases {
		got, _ := json.Marshal(PyFloat(c.in))
		if string(got) != c.want {
			t.Errorf("PyFloat(%v) = %s, want %s", c.in, got, c.want)
		}
	}
}

func TestIntervalSeconds(t *testing.T) {
	iv := pgtype.Interval{Microseconds: 32486489, Valid: true}
	if got := intervalSeconds(iv); got != PyFloat(32.486489) {
		t.Errorf("got %v", got)
	}
	iv = pgtype.Interval{Days: 1, Microseconds: 500000, Valid: true}
	if got := intervalSeconds(iv); got != PyFloat(86400.5) {
		t.Errorf("got %v", got)
	}
}

func TestRowMarshalPreservesOrderAndDedupes(t *testing.T) {
	row := Row{
		Columns: []string{"b", "a", "b"},
		values:  []any{1, 2, 3},
	}
	got, err := json.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	// dict() semantics: first position, last value.
	if string(got) != `{"b":3,"a":2}` {
		t.Errorf("got %s", got)
	}
}

func TestRowSetAndGet(t *testing.T) {
	row := NewRow()
	row.Set("x", 1)
	row.Set("y", "two")
	row.Set("x", 10)
	if row.GetInt("x") != 10 || row.GetString("y") != "two" {
		t.Errorf("unexpected values: %v %v", row.Get("x"), row.Get("y"))
	}
	got, _ := json.Marshal(row)
	if string(got) != `{"x":10,"y":"two"}` {
		t.Errorf("got %s", got)
	}
}
