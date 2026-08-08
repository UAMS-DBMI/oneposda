// posda-api is the Posda API server: a Go port of the Python/FastAPI
// implementation in posda/fastapi.
package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/config"
	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/server"
)

func main() {
	cfg := config.Load()

	if err := os.MkdirAll(cfg.TempStoragePath, 0o755); err != nil {
		log.Printf("warning: could not create temp storage path %s: %v",
			cfg.TempStoragePath, err)
	}

	ctx := context.Background()
	log.Println("database connecting")
	database, err := db.Connect(ctx, "posda_files")
	if err != nil {
		log.Fatalf("The database is not available: %v", err)
	}
	defer database.Close()
	log.Println("database connected")

	authService := auth.NewService(database, cfg.RedisHost, cfg.SystemToken)

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.APIPort),
		Handler: server.New(cfg, database, authService),
	}

	go func() {
		log.Printf("listening on %s", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)
	<-stop
	log.Println("SIGTERM received, shutting down...")

	shutdownCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
	}
}
