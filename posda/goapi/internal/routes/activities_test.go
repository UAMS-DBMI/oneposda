package routes

import (
	"testing"

	"tcia/posda-api/internal/db"
)

// Expected values observed from the live pydantic v2 serialization.
func TestPydanticDuration(t *testing.T) {
	cases := []struct {
		seconds float64
		want    string
	}{
		{32.486489, "PT32.486489S"},
		{0.078987, "PT0.078987S"},
		{0, "PT0S"},
		{60, "PT1M"},
		{3600, "PT1H"},
		{86400, "P1D"},
		{90061.5, "P1DT1H1M1.5S"},
		{-3, "-PT3S"},
	}
	for _, c := range cases {
		if got := pydanticDuration(db.PyFloat(c.seconds)); got != c.want {
			t.Errorf("pydanticDuration(%v) = %v, want %q", c.seconds, got, c.want)
		}
	}
}

func TestPydanticDatetime(t *testing.T) {
	if got := pydanticDatetime("2026-08-04T21:04:38.100177+00:00"); got != "2026-08-04T21:04:38.100177Z" {
		t.Errorf("got %v", got)
	}
	// naive timestamps pass through
	if got := pydanticDatetime("2026-08-04T21:04:38"); got != "2026-08-04T21:04:38" {
		t.Errorf("got %v", got)
	}
	if got := pydanticDatetime(nil); got != nil {
		t.Errorf("got %v", got)
	}
}

func TestParseSeriesSpec(t *testing.T) {
	s, err := parseSeriesSpec("1.2.3")
	if err != nil || s.UID != "1.2.3" || s.ActivityID != nil || s.TimepointID != nil {
		t.Errorf("plain: %+v err=%v", s, err)
	}
	s, err = parseSeriesSpec("1.2.3@45")
	if err != nil || s.UID != "1.2.3" || s.ActivityID == nil || *s.ActivityID != 45 {
		t.Errorf("activity: %+v err=%v", s, err)
	}
	s, err = parseSeriesSpec("1.2.3:99")
	if err != nil || s.UID != "1.2.3" || s.TimepointID == nil || *s.TimepointID != 99 {
		t.Errorf("timepoint: %+v err=%v", s, err)
	}
	if _, err = parseSeriesSpec("1.2.3@xx"); err == nil {
		t.Error("expected error for non-integer activity id")
	}
}
