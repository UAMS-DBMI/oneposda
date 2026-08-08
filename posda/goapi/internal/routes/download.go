package routes

import (
	"fmt"
	"mime"
	"net/http"
	"os/exec"

	"tcia/posda-api/internal/archive"
)

// registerDownload ports papi/routes/download.py. The router is
// mounted both under /v1/download and at the application root (the
// latter for backward compatibility), with no login requirement —
// access control is the security_hash in the URL.
func (a *App) registerDownload(mux *http.ServeMux) {
	for _, prefix := range []string{"", "/v1/download"} {
		a.public(mux, "GET "+prefix+"/file/{downloadable_file_id}/{hash}", a.downloadFile)
		a.public(mux, "GET "+prefix+"/dir/{downloadable_dir_id}/{hash}", a.downloadDir)
	}
}

// guessExtension mirrors Python's mimetypes.guess_extension for the
// mime types stored in downloadable_file.
func guessExtension(mimeType string) string {
	switch mimeType {
	case "text/plain":
		return ".txt"
	case "text/csv":
		return ".csv"
	case "text/html":
		return ".html"
	case "application/json":
		return ".json"
	case "application/pdf":
		return ".pdf"
	case "application/zip":
		return ".zip"
	case "application/gzip":
		return ".gz"
	}
	if exts, err := mime.ExtensionsByType(mimeType); err == nil && len(exts) > 0 {
		return exts[0]
	}
	return ""
}

func (a *App) downloadFile(w http.ResponseWriter, r *http.Request) error {
	id, err := pathInt(r, "downloadable_file_id")
	if err != nil {
		return err
	}
	hash := pathStr(r, "hash")

	row, found, err := a.DB.FetchOne(r.Context(), `
        select
            root_path || '/' || rel_path as file,
            size,
            mime_type,
            name as report_name
        from downloadable_file
        natural join file
        natural join file_location
        natural join file_storage_root
        natural left join background_subprocess_report
        where downloadable_file_id = $1
          and security_hash = $2
          and (valid_until is null or now() < valid_until)
    `, id, hash)
	if err != nil {
		return err
	}
	if !found {
		return errNoRecords
	}

	path := row.GetString("file")
	mimeType := row.GetString("mime_type")
	ext := guessExtension(mimeType)

	if queryBool(r, "process", false) {
		var cmd string
		if row.GetString("report_name") == "DciodvfySeriesReport" {
			cmd = fmt.Sprintf("/home/posda/posdatools/dciodvfymacro/run.sh %s", path)
		} else {
			cmd = fmt.Sprintf("/home/posda/posdatools/phimacro/run.sh %s", path)
		}

		// Matches asyncio.create_subprocess_shell: the command line is
		// interpreted by the shell, stdout and stderr are concatenated.
		proc := exec.CommandContext(r.Context(), "/bin/sh", "-c", cmd)
		stdout, err := proc.Output()
		var stderr []byte
		if exitErr, ok := err.(*exec.ExitError); ok {
			stderr = exitErr.Stderr
		} else if err != nil {
			return err
		}

		filename := fmt.Sprintf("downloaded_file_%d_macro%s", id, ext)
		w.Header().Set("Content-Type", mimeType)
		w.Header().Set("Content-Disposition",
			fmt.Sprintf(`attachment; filename="%s"`, filename))
		_, _ = w.Write(stdout)
		_, _ = w.Write(stderr)
		return nil
	}

	return serveFile(w, r, path,
		fmt.Sprintf("downloaded_file_%d%s", id, ext), nil)
}

func (a *App) downloadDir(w http.ResponseWriter, r *http.Request) error {
	id, err := pathInt(r, "downloadable_dir_id")
	if err != nil {
		return err
	}
	hash := pathStr(r, "hash")

	row, found, err := a.DB.FetchOne(r.Context(), `
        select
            path
        from downloadable_dir
        where downloadable_dir_id = $1
          and security_hash = $2
    `, id, hash)
	if err != nil {
		return err
	}
	if !found {
		return errNoRecords
	}

	return archive.StreamTarGz(w, row.GetString("path"),
		fmt.Sprintf("downloaded_dir_%d.tar.gz", id))
}
