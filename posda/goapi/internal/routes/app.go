// Package routes contains the HTTP handlers, one file per module,
// mirroring app/papi/routes/ in the Python implementation.
package routes

import (
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/config"
	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/httpx"
)

type App struct {
	Cfg  *config.Config
	DB   *db.DB
	Auth *auth.Service
}

// Register attaches every route to mux. Paths match the Python app
// exactly: /auth/*, /v1/*, and the legacy download routes at the root.
func (a *App) Register(mux *http.ServeMux) {
	// FastAPI returns JSON bodies for 404s; match that for unknown paths.
	mux.Handle("/", httpx.HandlerFunc(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusNotFound, "Not Found")
	}))

	a.registerAuth(mux)
	a.registerOther(mux)
	a.registerCollections(mux)
	a.registerStudies(mux)
	a.registerSeries(mux)
	a.registerFiles(mux)
	a.registerIECs(mux)
	a.registerDump(mux)
	a.registerDownload(mux)
	a.registerVRStatus(mux)
	a.registerDashboard(mux)
	a.registerROIs(mux)
	a.registerImporter(mux)
	a.registerSendToPublicStatus(mux)
	a.registerDicomRoots(mux)
	a.registerWorker(mux)
	a.registerPathology(mux)
	a.registerWork(mux)
	a.registerDeface(mux)
	a.registerEdits(mux)
	a.registerNifti(mux)
	a.registerSysStatus(mux)
	a.registerMasking(mux)
	a.registerWadoRS(mux)
	a.registerSegs(mux)
	a.registerActivities(mux)
	a.registerVisualReviews(mux)
}

// public registers a route that does not require login.
func (a *App) public(mux *http.ServeMux, pattern string, h httpx.HandlerFunc) {
	mux.Handle(pattern, h)
}

// protected registers a route behind the login middleware.
func (a *App) protected(mux *http.ServeMux, pattern string, h httpx.HandlerFunc) {
	mux.Handle(pattern, a.Auth.Middleware(h))
}

// --- request parameter helpers ---------------------------------------

func pathStr(r *http.Request, name string) string {
	return r.PathValue(name)
}

func pathInt(r *http.Request, name string) (int64, error) {
	v, err := strconv.ParseInt(r.PathValue(name), 10, 64)
	if err != nil {
		return 0, httpx.NewError(http.StatusUnprocessableEntity,
			fmt.Sprintf("path parameter %q must be an integer", name))
	}
	return v, nil
}

// queryStr returns a query parameter, or the fallback when absent.
func queryStr(r *http.Request, name, fallback string) string {
	if !r.URL.Query().Has(name) {
		return fallback
	}
	return r.URL.Query().Get(name)
}

// queryIntPtr returns an optional integer query parameter (nil when
// absent), erroring like FastAPI when the value isn't an integer.
func queryIntPtr(r *http.Request, name string) (*int64, error) {
	if !r.URL.Query().Has(name) {
		return nil, nil
	}
	v, err := strconv.ParseInt(r.URL.Query().Get(name), 10, 64)
	if err != nil {
		return nil, httpx.NewError(http.StatusUnprocessableEntity,
			fmt.Sprintf("query parameter %q must be an integer", name))
	}
	return &v, nil
}

func queryInt(r *http.Request, name string, fallback int64) (int64, error) {
	p, err := queryIntPtr(r, name)
	if err != nil {
		return 0, err
	}
	if p == nil {
		return fallback, nil
	}
	return *p, nil
}

func queryBool(r *http.Request, name string, fallback bool) bool {
	if !r.URL.Query().Has(name) {
		return fallback
	}
	switch strings.ToLower(r.URL.Query().Get(name)) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	}
	return fallback
}

// --- response helpers -------------------------------------------------

// errNoRecords mirrors the common `HTTPException(404, "no records
// returned")` used throughout the Python code.
var errNoRecords = httpx.NewError(http.StatusNotFound, "no records returned")

// fetchJSON runs a query and writes all rows as a JSON array.
func (a *App) fetchJSON(w http.ResponseWriter, r *http.Request, sql string, args ...any) error {
	rows, err := a.DB.Fetch(r.Context(), sql, args...)
	if err != nil {
		return err
	}
	return httpx.JSON(w, rows)
}

// fetchOneJSON writes the first row as a JSON object. When the query
// matches nothing it writes [] — the Python Database.fetch_one helper
// returns an empty list in that case, and FastAPI serializes it as-is.
func (a *App) fetchOneJSON(w http.ResponseWriter, r *http.Request, sql string, args ...any) error {
	row, found, err := a.DB.FetchOne(r.Context(), sql, args...)
	if err != nil {
		return err
	}
	if !found {
		return httpx.JSON(w, []any{})
	}
	return httpx.JSON(w, row)
}

// firstColumn extracts the first column of every row.
func firstColumn(rows []db.Row) []any {
	out := make([]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, row.Values()[0])
	}
	return out
}

// fetchFirstColumn runs a query and writes the first column of each row
// as a JSON array (the `[x[0] for x in rows]` idiom).
func (a *App) fetchFirstColumn(w http.ResponseWriter, r *http.Request, sql string, args ...any) error {
	rows, err := a.DB.Fetch(r.Context(), sql, args...)
	if err != nil {
		return err
	}
	return httpx.JSON(w, firstColumn(rows))
}

// isUniqueViolation reports whether err is a Postgres unique_violation.
func isUniqueViolation(err error) bool {
	return pgErrCode(err) == "23505"
}

// isForeignKeyViolation reports whether err is a foreign_key_violation.
func isForeignKeyViolation(err error) bool {
	return pgErrCode(err) == "23503"
}

// isInvalidTextRepresentation reports whether err is Postgres error
// 22P02 (e.g. bad input for an enum type).
func isInvalidTextRepresentation(err error) bool {
	return pgErrCode(err) == "22P02"
}

func pgErrCode(err error) string {
	var pgErr interface{ SQLState() string }
	if errors.As(err, &pgErr) {
		return pgErr.SQLState()
	}
	return ""
}
