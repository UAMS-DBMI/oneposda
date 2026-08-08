// Package archive streams zip and tar.gz downloads, replacing the
// Python zipstream/asynctar helpers with stdlib streaming writers.
package archive

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// StreamZip writes the given files as an uncompressed (STORED, like
// zipstream's default) zip archive directly to the response. Archive
// member names are the full paths with leading slashes stripped,
// matching Python's zipfile.write default arcname.
func StreamZip(w http.ResponseWriter, files []string, downloadName string) error {
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition",
		fmt.Sprintf(`attachment; filename="%s"`, downloadName))

	zw := zip.NewWriter(w)
	for _, path := range files {
		if err := addZipFile(zw, path); err != nil {
			// Headers are already sent; all we can do is abort the
			// stream so the client sees a truncated archive.
			log.Printf("zip stream %s aborted: %v", downloadName, err)
			return nil
		}
	}
	if err := zw.Close(); err != nil {
		log.Printf("zip stream %s failed to finalize: %v", downloadName, err)
	}
	return nil
}

func addZipFile(zw *zip.Writer, path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	info, err := f.Stat()
	if err != nil {
		return err
	}
	hdr := &zip.FileHeader{
		Name:     strings.TrimLeft(path, "/"),
		Method:   zip.Store,
		Modified: info.ModTime(),
	}
	hdr.SetMode(info.Mode())
	member, err := zw.CreateHeader(hdr)
	if err != nil {
		return err
	}
	_, err = io.Copy(member, f)
	return err
}

// StreamTarGz walks dir and streams its contents as a tar.gz archive,
// with member names relative to dir. Symlinks are followed
// (tarfile dereference=True).
func StreamTarGz(w http.ResponseWriter, dir, downloadName string) error {
	w.Header().Set("Content-Type", "application/gzip")
	w.Header().Set("Content-Disposition",
		fmt.Sprintf(`attachment; filename="%s"`, downloadName))

	gz, err := gzip.NewWriterLevel(w, gzip.BestCompression)
	if err != nil {
		return err
	}
	tw := tar.NewWriter(gz)

	walkErr := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(dir, path)
		if err != nil {
			return err
		}
		return addTarFile(tw, path, rel)
	})
	if walkErr != nil {
		log.Printf("tar stream %s aborted: %v", downloadName, walkErr)
	}
	if err := tw.Close(); err != nil {
		return err
	}
	return gz.Close()
}

func addTarFile(tw *tar.Writer, path, arcname string) error {
	// os.Stat (not Lstat) so symlinks are archived as regular files.
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return nil
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	hdr, err := tar.FileInfoHeader(info, "")
	if err != nil {
		return err
	}
	hdr.Name = arcname
	if err := tw.WriteHeader(hdr); err != nil {
		return err
	}
	_, err = io.Copy(tw, f)
	return err
}
