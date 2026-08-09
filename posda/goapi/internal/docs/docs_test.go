package docs

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHandlersServeEmbeddedAssets(t *testing.T) {
	cases := map[string]string{
		"GET /openapi.json":              "application/json",
		"GET /docs":                      "text/html; charset=utf-8",
		"GET /docs/swagger-ui.css":       "text/css",
		"GET /docs/swagger-ui-bundle.js": "application/javascript",
	}
	handlers := Handlers()
	for pattern, wantType := range cases {
		h, ok := handlers[pattern]
		if !ok {
			t.Fatalf("no handler registered for %q", pattern)
		}
		path := strings.TrimPrefix(pattern, "GET ")
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, httptest.NewRequest("GET", path, nil))

		if rec.Code != http.StatusOK {
			t.Errorf("%s: status = %d", path, rec.Code)
		}
		if got := rec.Header().Get("Content-Type"); got != wantType {
			t.Errorf("%s: Content-Type = %q, want %q", path, got, wantType)
		}
		if rec.Body.Len() == 0 {
			t.Errorf("%s: empty body", path)
		}
	}
}

func TestOpenAPIDocumentIsUsable(t *testing.T) {
	var spec struct {
		OpenAPI string                            `json:"openapi"`
		Info    struct{ Title string }            `json:"info"`
		Paths   map[string]map[string]interface{} `json:"paths"`
	}
	if err := json.Unmarshal(openAPIJSON, &spec); err != nil {
		t.Fatalf("embedded openapi.json does not parse: %v", err)
	}
	if spec.OpenAPI != "3.1.0" {
		t.Errorf("openapi = %q", spec.OpenAPI)
	}
	if spec.Info.Title != "PosdaAPI" {
		t.Errorf("title = %q", spec.Info.Title)
	}
	// The document is generated from the TypeScript port; if the copy
	// here were stale or truncated this is what would notice.
	if len(spec.Paths) < 150 {
		t.Errorf("only %d paths in the embedded document", len(spec.Paths))
	}
	if _, ok := spec.Paths["/v1/collections"]; !ok {
		t.Error("/v1/collections missing from the embedded document")
	}
}

func TestDocsPageUsesRelativeAssetURLs(t *testing.T) {
	// Absolute URLs would break /papi/docs behind the nginx proxy.
	html := string(docsHTML)
	for _, want := range []string{
		`href="docs/swagger-ui.css"`,
		`src="docs/swagger-ui-bundle.js"`,
		`url: "openapi.json"`,
	} {
		if !strings.Contains(html, want) {
			t.Errorf("docs.html does not contain %s", want)
		}
	}
}
