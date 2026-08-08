package server

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestStripRootPath(t *testing.T) {
	var seen string
	h := stripRootPath(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = r.URL.Path
	}))

	cases := []struct{ in, want string }{
		{"/papi/v1/collections/", "/v1/collections/"},
		{"/papi/auth/token", "/auth/token"},
		{"/v1/collections/", "/v1/collections/"}, // direct access, no prefix
		{"/papize/other", "/papize/other"},       // not the prefix
		{"/papi", "/papi"},                       // bare prefix passes through
	}
	for _, c := range cases {
		req := httptest.NewRequest("GET", c.in, nil)
		h.ServeHTTP(httptest.NewRecorder(), req)
		if seen != c.want {
			t.Errorf("path %q dispatched as %q, want %q", c.in, seen, c.want)
		}
	}
}
