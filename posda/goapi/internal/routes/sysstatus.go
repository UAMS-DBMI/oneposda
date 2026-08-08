package routes

import (
	"fmt"
	"net/http"
)

// registerSysStatus ports papi/routes/sysstatus.py. This route has no
// login requirement.
func (a *App) registerSysStatus(mux *http.ServeMux) {
	a.public(mux, "GET /v1/sysstatus/system/{system_key}",
		func(w http.ResponseWriter, r *http.Request) error {
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			_, err := fmt.Fprintf(w, "<i>Test Message for %s</i>", pathStr(r, "system_key"))
			return err
		})
}
