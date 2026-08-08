package routes

import (
	"net/http"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/httpx"
)

// registerOther ports papi/routes/other.py (test/debug endpoints).
func (a *App) registerOther(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/other/streamtest",
		func(w http.ResponseWriter, r *http.Request) error {
			w.Header().Set("Content-Type", "application/octet-stream")
			for range 50 {
				if _, err := w.Write([]byte{1, 2, 3}); err != nil {
					return nil
				}
			}
			return nil
		})

	a.protected(mux, "GET /v1/other/tar",
		func(w http.ResponseWriter, r *http.Request) error {
			w.Header().Set("Content-Type", "application/octet-stream")
			for i := range 50 {
				chunk := []byte{0xab, 0xcd, 0xde, 0xff, byte(i)}
				if _, err := w.Write(chunk); err != nil {
					return nil
				}
			}
			return nil
		})

	a.protected(mux, "GET /v1/other/asynctar",
		func(w http.ResponseWriter, r *http.Request) error {
			// The Python endpoint calls asynctar.stream(), which does
			// not exist, so it has always responded 500.
			return httpx.ErrInternal
		})

	a.protected(mux, "GET /v1/other/testme",
		func(w http.ResponseWriter, r *http.Request) error {
			return httpx.JSON(w, auth.CurrentUser(r))
		})

	a.protected(mux, "GET /v1/other/query/{query_name}/execute",
		func(w http.ResponseWriter, r *http.Request) error {
			params := map[string]any{}
			for k, v := range r.URL.Query() {
				if len(v) > 0 {
					params[k] = v[len(v)-1]
				}
			}
			return httpx.JSON(w, map[string]any{
				"query":  pathStr(r, "query_name"),
				"params": params,
				"user":   auth.CurrentUser(r),
			})
		})
}
