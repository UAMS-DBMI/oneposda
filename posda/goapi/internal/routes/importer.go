package routes

import (
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"sync"

	"github.com/jackc/pgx/v5"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/httpx"
)

// rootMapCache caches the file_storage_root table, mirroring the
// module-level ROOT_MAP_CACHE (loaded once, never invalidated).
var (
	rootMapMu    sync.Mutex
	rootMapCache map[string]int64
)

// registerImporter ports papi/routes/importer.py. Import operations do
// not require a logged in user.
func (a *App) registerImporter(mux *http.ServeMux) {
	a.public(mux, "PUT /v1/import/event", a.importEvent)
	a.public(mux, "POST /v1/import/event/{import_event_id}/close", a.closeImportEvent)
	a.public(mux, "POST /v1/import/test", a.importTest)
	a.public(mux, "PUT /v1/import/file", a.importFile)
	a.public(mux, "POST /v1/import/file", a.importFile)
	a.public(mux, "POST /v1/import/file_in_place", a.importFileInPlace)
}

func (a *App) importEvent(w http.ResponseWriter, r *http.Request) error {
	if !r.URL.Query().Has("source") {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"query parameter \"source\" is required")
	}
	source := r.URL.Query().Get("source")
	origin := r.URL.Query().Get("origin")
	expectedCount, err := queryIntPtr(r, "expected_count")
	if err != nil {
		return err
	}

	var originArg any
	if origin != "" {
		originArg = origin
	}

	var eventID int64
	err = a.DB.Tx(r.Context(), func(tx pgx.Tx) error {
		eventID, err = createImportEvent(r, tx, source, originArg, expectedCount)
		return err
	})
	if err != nil {
		return err
	}

	return httpx.JSON(w, map[string]any{
		"status":          "success",
		"import_event_id": eventID,
	})
}

func createImportEvent(r *http.Request, tx pgx.Tx, comment string, origin any, expectedCount *int64) (int64, error) {
	row, found, err := db.FetchOneTx(r.Context(), tx, `
        insert into import_event
        (import_type, import_comment, import_time, import_origin, import_expected_count)
        values
        ($1, $2, now(), $3, $4)
        returning import_event_id
    `, "posda-api import", comment, origin, expectedCount)
	if err != nil {
		return 0, err
	}
	if !found {
		return 0, fmt.Errorf("import_event insert returned no row")
	}
	return row.GetInt("import_event_id"), nil
}

func (a *App) closeImportEvent(w http.ResponseWriter, r *http.Request) error {
	eventID, err := pathInt(r, "import_event_id")
	if err != nil {
		return err
	}
	_, found, err := a.DB.FetchOne(r.Context(), `
        update import_event
        set import_close_time = now()
        where import_event_id = $1
        returning import_event_id
    `, eventID)
	if err != nil {
		return err
	}
	if !found {
		return httpx.NewError(http.StatusUnprocessableEntity, "invalid import_event_id")
	}
	return httpx.JSON(w, map[string]any{"status": "success"})
}

func (a *App) importTest(w http.ResponseWriter, r *http.Request) error {
	err := a.DB.Tx(r.Context(), func(tx pgx.Tx) error {
		_, _, err := createOrGetFileID(r, tx, "bogus1", 37)
		return err
	})
	if err != nil {
		return err
	}
	return httpx.JSON(w, "Success")
}

func (a *App) importFile(w http.ResponseWriter, r *http.Request) error {
	if !r.URL.Query().Has("digest") {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"query parameter \"digest\" is required")
	}
	digest := r.URL.Query().Get("digest")
	importEventID, err := queryIntPtr(r, "import_event_id")
	if err != nil {
		return err
	}
	localpath := r.URL.Query().Get("localpath")
	subprocessInvocationID, err := queryIntPtr(r, "subprocess_invocation_id")
	if err != nil {
		return err
	}
	fromFileDigest := r.URL.Query().Get("from_file_digest")

	// Spool the request body to a temp file, hashing as we go.
	tmp, err := os.CreateTemp(a.Cfg.TempStoragePath, "upload*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	hash := md5.New()
	bytesRead, err := io.Copy(io.MultiWriter(tmp, hash), r.Body)
	closeErr := tmp.Close()
	if err != nil || closeErr != nil {
		os.Remove(tmpName)
		if err == nil {
			err = closeErr
		}
		return err
	}

	computedDigest := hex.EncodeToString(hash.Sum(nil))
	if computedDigest != digest {
		os.Remove(tmpName)
		return httpx.NewError(http.StatusUnprocessableEntity,
			"digest of received bytes does not match supplied digest")
	}

	var response map[string]any
	err = a.DB.Tx(r.Context(), func(tx pgx.Tx) error {
		created, fileID, err := createOrGetFileID(r, tx, computedDigest, bytesRead)
		if err != nil {
			return err
		}

		if created {
			rootID, relPath, err := a.copyFileIntoPlace(tmpName, computedDigest)
			if err != nil {
				return err
			}
			if err := createFileLocation(r, tx, fileID, rootID, relPath); err != nil {
				return err
			}
			if err := setReadyToProcess(r, tx, fileID, true); err != nil {
				return err
			}
		} else {
			os.Remove(tmpName)
		}

		eventID, err := ensureImportEvent(r, tx, importEventID, "single-file api import")
		if err != nil {
			return err
		}
		if err := createFileImport(r, tx, fileID, eventID, localpath); err != nil {
			return err
		}

		if subprocessInvocationID != nil && fromFileDigest != "" {
			_, err := tx.Exec(r.Context(), `
                insert into dicom_edit_compare
                values ($1, $2, 0, 0, null, $3)
            `, fromFileDigest, digest, *subprocessInvocationID)
			if err != nil {
				return err
			}
		}

		response = map[string]any{
			"status":  "success",
			"size":    bytesRead,
			"digest":  computedDigest,
			"file_id": fileID,
			"created": created,
		}
		return nil
	})
	if err != nil {
		return err
	}
	return httpx.JSON(w, response)
}

func (a *App) importFileInPlace(w http.ResponseWriter, r *http.Request) error {
	localpath := r.URL.Query().Get("localpath")
	if localpath == "" {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"query parameter \"localpath\" is required")
	}
	importEventID, err := queryIntPtr(r, "import_event_id")
	if err != nil {
		return err
	}
	skipProcessing := queryBool(r, "skip_processing", false)
	digest := r.URL.Query().Get("digest")

	rootMap, err := a.rootMap(r)
	if err != nil {
		return err
	}
	matchRoot, relPath, err := findBestRoot(rootMap, localpath)
	if err != nil {
		return err
	}

	var size int64
	if digest != "" {
		stat, err := os.Stat(localpath)
		if err != nil {
			return httpx.NewError(http.StatusUnprocessableEntity, "no such file")
		}
		size = stat.Size()
	} else {
		size, digest, err = md5sumFile(localpath)
		if err != nil {
			return httpx.NewError(http.StatusUnprocessableEntity, "no such file")
		}
	}

	var response map[string]any
	err = a.DB.Tx(r.Context(), func(tx pgx.Tx) error {
		created, fileID, err := createOrGetFileID(r, tx, digest, size)
		if err != nil {
			return err
		}

		if created {
			if err := createFileLocation(r, tx, fileID, matchRoot, relPath); err != nil {
				return err
			}
			if err := setReadyToProcess(r, tx, fileID, !skipProcessing); err != nil {
				return err
			}
		}

		eventID, err := ensureImportEvent(r, tx, importEventID,
			"single-file in-place api import")
		if err != nil {
			return err
		}
		if err := createFileImport(r, tx, fileID, eventID, localpath); err != nil {
			return err
		}

		response = map[string]any{
			"status":  "success",
			"size":    size,
			"digest":  digest,
			"file_id": fileID,
			"created": created,
		}
		return nil
	})
	if err != nil {
		return err
	}
	return httpx.JSON(w, response)
}

// --- helpers ----------------------------------------------------------

func (a *App) rootMap(r *http.Request) (map[string]int64, error) {
	rootMapMu.Lock()
	defer rootMapMu.Unlock()
	if rootMapCache != nil {
		return rootMapCache, nil
	}
	rows, err := a.DB.Fetch(r.Context(), `
        select * from file_storage_root
        order by file_storage_root_id
    `)
	if err != nil {
		return nil, err
	}
	m := make(map[string]int64, len(rows))
	for _, row := range rows {
		m[row.GetString("root_path")] = row.GetInt("file_storage_root_id")
	}
	rootMapCache = m
	return m, nil
}

// findBestRoot picks the longest storage root that prefixes path.
func findBestRoot(rootMap map[string]int64, path string) (int64, string, error) {
	type candidate struct {
		rootLen int
		rootID  int64
		relPath string
	}
	var candidates []candidate
	for root, id := range rootMap {
		if len(path) > len(root) && path[:len(root)] == root {
			relPath := path[len(root)+1:]
			candidates = append(candidates, candidate{
				rootLen: len(path) - len(relPath),
				rootID:  id,
				relPath: relPath,
			})
		}
	}
	if len(candidates) == 0 {
		return 0, "", httpx.NewError(http.StatusUnprocessableEntity,
			"no matching file_storage_root")
	}
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].rootLen > candidates[j].rootLen
	})
	return candidates[0].rootID, candidates[0].relPath, nil
}

func md5sumFile(path string) (int64, string, error) {
	f, err := os.Open(path)
	if err != nil {
		return 0, "", err
	}
	defer f.Close()
	hash := md5.New()
	size, err := io.Copy(hash, f)
	if err != nil {
		return 0, "", err
	}
	return size, hex.EncodeToString(hash.Sum(nil)), nil
}

// copyFileIntoPlace moves the spooled upload into the storage tree
// (sharded by digest prefix) and returns the root id and rel path.
func (a *App) copyFileIntoPlace(tmpName, digest string) (int64, string, error) {
	shard := filepath.Join(digest[0:2], digest[2:4], digest[4:6])
	relPath := filepath.Join(shard, digest)

	realPath := filepath.Join(a.Cfg.FileStoragePath, shard)
	if err := os.MkdirAll(realPath, 0o755); err != nil {
		return 0, "", err
	}
	if err := os.Rename(tmpName, filepath.Join(a.Cfg.FileStoragePath, relPath)); err != nil {
		return 0, "", err
	}
	return int64(a.Cfg.FileStorageRootID), relPath, nil
}

func ensureImportEvent(r *http.Request, tx pgx.Tx, eventID *int64, comment string) (int64, error) {
	if eventID != nil {
		return *eventID, nil
	}
	return createImportEvent(r, tx, comment, nil, nil)
}

func setReadyToProcess(r *http.Request, tx pgx.Tx, fileID int64, ready bool) error {
	_, err := tx.Exec(r.Context(), `
        update file
        set ready_to_process = $2
        where file_id = $1
    `, fileID, ready)
	return err
}

func createFileLocation(r *http.Request, tx pgx.Tx, fileID, rootID int64, relPath string) error {
	_, err := tx.Exec(r.Context(), `
        insert into file_location
        (file_id, file_storage_root_id, rel_path)
        values
        ($1, $2, $3)
    `, fileID, rootID, relPath)
	return err
}

func createFileImport(r *http.Request, tx pgx.Tx, fileID, importEventID int64, localpath string) error {
	var localpathArg any
	if localpath != "" {
		localpathArg = localpath
	}
	_, err := tx.Exec(r.Context(), `
        insert into file_import
        values
        ($1, $2, $3, $4, $5, now())
    `, importEventID, fileID, nil, nil, localpathArg)
	return err
}

func createOrGetFileID(r *http.Request, tx pgx.Tx, digest string, size int64) (bool, int64, error) {
	row, found, err := db.FetchOneTx(r.Context(), tx, `
        insert into file
        (digest, size, processing_priority)
        values
        ($1, $2, 1)
        on conflict do nothing
        returning file_id
    `, digest, size)
	if err != nil {
		return false, 0, err
	}
	if found {
		return true, row.GetInt("file_id"), nil
	}

	row, found, err = db.FetchOneTx(r.Context(), tx, `
        select file_id
        from file
        where digest = $1
    `, digest)
	if err != nil {
		return false, 0, err
	}
	if !found {
		return false, 0, fmt.Errorf("file with digest %s neither inserted nor found", digest)
	}
	return false, row.GetInt("file_id"), nil
}
