// Package server assembles the HTTP handler: routes plus middleware.
package server

import (
	"net/http"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/config"
	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/routes"
)

// New builds the complete HTTP handler for the API.
func New(cfg *config.Config, database *db.DB, authService *auth.Service) http.Handler {
	app := &routes.App{
		Cfg:  cfg,
		DB:   database,
		Auth: authService,
	}
	mux := http.NewServeMux()
	app.Register(mux)
	return Gzip(mux)
}
