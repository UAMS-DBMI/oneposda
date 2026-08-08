package routes

import (
	"fmt"
	"net/http"
	"os/exec"
	"unicode/utf8"

	"tcia/posda-api/internal/httpx"
)

// registerDump ports papi/routes/dump.py: an HTML-formatted DICOM dump
// produced by an external script.
func (a *App) registerDump(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/dump/{file_id}", a.dumpDicom)
}

func (a *App) dumpDicom(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}

	row, found, err := a.DB.FetchOne(r.Context(), `
        select root_path || '/' || rel_path as file
        from
            file_location
            natural join file_storage_root
        where file_id = $1
    `, fileID)
	if err != nil {
		return err
	}
	if !found {
		return httpx.NewError(http.StatusNotFound,
			fmt.Sprintf("file_id %d does not exist", fileID))
	}

	out, err := exec.CommandContext(r.Context(), a.Cfg.DumpScript,
		row.GetString("file")).Output()
	if err != nil {
		return fmt.Errorf("dump script failed: %w", err)
	}

	// The Python version decodes as utf-8 and falls back to a chardet
	// guess; here anything that isn't valid utf-8 is treated as
	// latin-1, which covers the DICOM text encodings seen in practice.
	body := out
	if !utf8.Valid(out) {
		body = latin1ToUTF8(out)
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, err = w.Write(body)
	return err
}

func latin1ToUTF8(b []byte) []byte {
	out := make([]byte, 0, len(b)*2)
	for _, c := range b {
		out = utf8.AppendRune(out, rune(c))
	}
	return out
}
