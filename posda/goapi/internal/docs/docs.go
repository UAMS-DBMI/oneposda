// Package docs serves the OpenAPI document and its Swagger UI.
//
// The document is generated from the TypeScript port's route
// annotations (posda/tsapi/scripts/genopenapi.ts, run via `make
// openapi`), which writes an identical copy here. go:embed cannot reach
// outside the module, so the copy is checked in rather than symlinked.
// The UI assets are vendored so /docs works without outbound internet.
package docs

import (
	_ "embed"
	"net/http"
)

//go:embed openapi.json
var openAPIJSON []byte

//go:embed swagger-ui/docs.html
var docsHTML []byte

//go:embed swagger-ui/swagger-ui.css
var swaggerCSS []byte

//go:embed swagger-ui/swagger-ui-bundle.js
var swaggerJS []byte

// A year — the assets are versioned by the image they ship in.
const assetCache = "public, max-age=31536000, immutable"

// Handlers returns the documentation routes, keyed by mux pattern.
// The caller registers them without the login middleware, matching
// FastAPI's public /docs and /openapi.json.
func Handlers() map[string]http.Handler {
	return map[string]http.Handler{
		"GET /openapi.json":              static(openAPIJSON, "application/json", ""),
		"GET /docs":                      static(docsHTML, "text/html; charset=utf-8", ""),
		"GET /docs/swagger-ui.css":       static(swaggerCSS, "text/css", assetCache),
		"GET /docs/swagger-ui-bundle.js": static(swaggerJS, "application/javascript", assetCache),
	}
}

func static(body []byte, contentType, cacheControl string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", contentType)
		if cacheControl != "" {
			w.Header().Set("Cache-Control", cacheControl)
		}
		_, _ = w.Write(body)
	})
}
