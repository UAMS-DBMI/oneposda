package routes

import (
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"

	"tcia/posda-api/internal/httpx"
)

// decodeJSONBody decodes a JSON request body into dst, returning a 422
// (FastAPI's validation status) when the body cannot be parsed.
func decodeJSONBody(r *http.Request, dst any) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	if len(body) == 0 {
		body = []byte("{}")
	}
	if err := json.Unmarshal(body, dst); err != nil {
		return httpx.NewError(http.StatusUnprocessableEntity,
			fmt.Sprintf("invalid JSON body: %v", err))
	}
	return nil
}

// guessMediaType mirrors Starlette's FileResponse default: mimetypes
// guess by extension, falling back to text/plain.
func guessMediaType(path string) string {
	if mt := mime.TypeByExtension(filepath.Ext(path)); mt != "" {
		return mt
	}
	return "text/plain; charset=utf-8"
}

// serveFile streams a file like Starlette's FileResponse. When
// downloadName is non-empty a Content-Disposition attachment header is
// added. extraHeaders are set before the body is written.
func serveFile(w http.ResponseWriter, r *http.Request, path, downloadName string,
	extraHeaders map[string]string) error {

	f, err := os.Open(path)
	if err != nil {
		return httpx.NewError(http.StatusNotFound, "File not found on disk")
	}
	defer f.Close()

	info, err := f.Stat()
	if err != nil {
		return err
	}

	w.Header().Set("Content-Type", guessMediaType(path))
	if downloadName != "" {
		w.Header().Set("Content-Disposition",
			fmt.Sprintf(`attachment; filename="%s"`, downloadName))
	}
	for k, v := range extraHeaders {
		w.Header().Set(k, v)
	}
	http.ServeContent(w, r, "", info.ModTime(), f)
	return nil
}

// readFileFrom returns the contents of path starting at offset,
// mirroring the Python "seek then read to EOF" pattern used for pixel
// data.
func readFileFrom(path string, offset int64) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	if _, err := f.Seek(offset, io.SeekStart); err != nil {
		return nil, err
	}
	return io.ReadAll(f)
}
