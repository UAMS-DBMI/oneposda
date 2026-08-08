// Package server assembles the HTTP handler: routes plus middleware.
package server

import (
	"net/http"
	"strings"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/config"
	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/routes"
)

// rootPath matches FastAPI's root_path="/papi": the nginx proxy
// forwards the full request path including this prefix, and the app is
// expected to strip it. Requests without the prefix (direct access)
// work as well.
const rootPath = "/papi"

// New builds the complete HTTP handler for the API.
func New(cfg *config.Config, database *db.DB, authService *auth.Service) http.Handler {
	app := &routes.App{
		Cfg:  cfg,
		DB:   database,
		Auth: authService,
	}
	mux := http.NewServeMux()
	app.Register(mux)
	return Gzip(stripRootPath(mux))
}

func stripRootPath(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if p, ok := strings.CutPrefix(r.URL.Path, rootPath+"/"); ok {
			r2 := r.Clone(r.Context())
			r2.URL.Path = "/" + p
			if rp, ok := strings.CutPrefix(r.URL.RawPath, rootPath+"/"); ok {
				r2.URL.RawPath = "/" + rp
			}
			next.ServeHTTP(w, r2)
			return
		}
		next.ServeHTTP(w, r)
	})
}
