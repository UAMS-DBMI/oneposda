package routes

import (
	"net/http"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/httpx"
)

// registerAuth ports papi/routes/auth.py.
func (a *App) registerAuth(mux *http.ServeMux) {
	a.public(mux, "POST /auth/token", a.Auth.Login)

	a.protected(mux, "GET /auth/users/me",
		func(w http.ResponseWriter, r *http.Request) error {
			return httpx.JSON(w, auth.CurrentUser(r))
		})

	a.public(mux, "GET /auth/test",
		func(w http.ResponseWriter, r *http.Request) error {
			return httpx.JSON(w, map[string]any{"message": "everything looks good"})
		})
}
