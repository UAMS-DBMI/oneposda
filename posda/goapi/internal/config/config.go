// Package config loads all runtime configuration from the environment,
// mirroring the environment variables used by the Python implementation.
package config

import (
	"os"
	"strconv"
)

type Config struct {
	// APIPort is the port the HTTP server listens on (API_PORT).
	APIPort int

	// APIURL is the externally-visible URL of this API (POSDA_API_URL).
	// It is embedded in OHIF viewer configs and dicomweb URLs.
	APIURL string

	// RedisHost is the hostname of the redis server used for login
	// tokens (POSDA_REDIS_HOST).
	RedisHost string

	// SystemToken is a static token that authenticates as the "system"
	// user (POSDA_API_SYSTEM_TOKEN).
	SystemToken string

	// FileStoragePath is where newly imported files are stored
	// (FILE_STORAGE_PATH).
	FileStoragePath string

	// TempStoragePath is where uploads are spooled before being moved
	// into place (TEMP_STORAGE_PATH).
	TempStoragePath string

	// FileStorageRootID is the file_storage_root_id corresponding to
	// FileStoragePath (FILE_STORAGE_ROOT).
	FileStorageRootID int

	// DumpScript is the script used to render DICOM dumps (see
	// /v1/dump/{file_id}). The default matches the hard-coded path used
	// by the Python implementation's docker image.
	DumpScript string
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getenvInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func Load() *Config {
	return &Config{
		APIPort:           getenvInt("API_PORT", 8087),
		APIURL:            os.Getenv("POSDA_API_URL"),
		RedisHost:         getenv("POSDA_REDIS_HOST", "redis"),
		SystemToken:       getenv("POSDA_API_SYSTEM_TOKEN", "nologinallowed"),
		FileStoragePath:   getenv("FILE_STORAGE_PATH", "/home/posda/cache/created"),
		TempStoragePath:   getenv("TEMP_STORAGE_PATH", "/home/posda/cache/temp"),
		FileStorageRootID: getenvInt("FILE_STORAGE_ROOT", 3),
		DumpScript:        getenv("DUMP_SCRIPT", "/fastapi/dump_dicom.sh"),
	}
}
