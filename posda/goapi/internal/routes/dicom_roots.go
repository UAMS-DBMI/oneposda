package routes

import (
	"net/http"
	"strconv"
	"strings"

	"tcia/posda-api/internal/httpx"
)

// registerDicomRoots ports papi/routes/dicom_roots.py.
func (a *App) registerDicomRoots(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "test error")
	})
	a.public(mux, "GET /v1/dicom_roots", notAllowed)
	a.public(mux, "GET /v1/dicom_roots/{$}", notAllowed)

	a.protected(mux, "GET /v1/dicom_roots/searchRoots", a.searchRoots)
	a.protected(mux, "GET /v1/dicom_roots/findCollectionNameFromCode/{collection_code}", a.findCollectionName)
	a.protected(mux, "GET /v1/dicom_roots/findSiteNameFromCode/{site_code}", a.findSiteName)
	a.protected(mux, "POST /v1/dicom_roots/addNewSubmission", a.addNewSubmission)
}

func (a *App) searchRoots(w http.ResponseWriter, r *http.Request) error {
	where := "where 1 = 1 "
	var values []any

	addLike := func(param, clause string) {
		if r.URL.Query().Has(param) {
			values = append(values, r.URL.Query().Get(param))
			where += "and " + clause + " like $" + strconv.Itoa(len(values)) + " "
		}
	}

	addLike("site_code", "site_code")
	addLike("collection_code", "collection_code")
	addLike("site_name", "site_name")
	addLike("collection_name", "collection_name")
	addLike("patient_id_prefix", "patient_id_prefix")
	addLike("body_part", "body_part")

	if r.URL.Query().Has("access_type") {
		at := r.URL.Query().Get("access_type")
		if at != "public" && at != "limited" {
			return httpx.NewError(http.StatusUnprocessableEntity,
				"access_type must be one of: public, limited")
		}
		values = append(values, at)
		where += "and access_type = $" + strconv.Itoa(len(values)) + " "
	}

	addLike("baseline_date", "baseline_date::text")
	addLike("date_shift", "date_shift::text")

	query := strings.Replace(`
        select
        b.*,
        c.*,
        a.patient_id_prefix,
        a.body_part,
        a.access_type,
        a.baseline_date,
        a.date_shift,
        a.uid_root
        from
        	submissions a
        	natural join collection_codes b
        	natural join site_codes c
            {}
    `, "{}", where, 1)

	return a.fetchJSON(w, r, query, values...)
}

func (a *App) findCollectionName(w http.ResponseWriter, r *http.Request) error {
	code, err := pathInt(r, "collection_code")
	if err != nil {
		return err
	}
	row, found, err := a.DB.FetchOne(r.Context(), `
        select
         collection_name
        from
         collection_codes
        where
         collection_code = $1
        `, strconv.FormatInt(code, 10))
	if err != nil {
		return err
	}
	if !found {
		return httpx.NewError(http.StatusInternalServerError, "Internal Server Error")
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, err = w.Write([]byte(row.GetString("collection_name")))
	return err
}

func (a *App) findSiteName(w http.ResponseWriter, r *http.Request) error {
	code, err := pathInt(r, "site_code")
	if err != nil {
		return err
	}
	row, found, err := a.DB.FetchOne(r.Context(), `
       select
        site_name
       from
        site_codes
       where
        site_code = $1
       `, strconv.FormatInt(code, 10))
	if err != nil {
		return err
	}
	if !found {
		return httpx.NewError(http.StatusInternalServerError, "Internal Server Error")
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, err = w.Write([]byte(row.GetString("site_name")))
	return err
}

type submission struct {
	InputSiteCode        int64   `json:"input_site_code"`
	InputSiteName        string  `json:"input_site_name"`
	InputCollectionCode  int64   `json:"input_collection_code"`
	InputCollectionName  string  `json:"input_collection_name"`
	InputPatientIDPrefix string  `json:"input_patient_id_prefix"`
	InputBodyPart        string  `json:"input_body_part"`
	InputAccessType      string  `json:"input_access_type"`
	InputBaselineDate    *string `json:"input_baseline_date"`
	InputDateShift       *string `json:"input_date_shift"`
	InputUIDRoot         *string `json:"input_uid_root"`
}

func (a *App) addNewSubmission(w http.ResponseWriter, r *http.Request) error {
	var sub submission
	if err := decodeJSONBody(r, &sub); err != nil {
		return err
	}
	siteCode := strconv.FormatInt(sub.InputSiteCode, 10)
	collectionCode := strconv.FormatInt(sub.InputCollectionCode, 10)

	// The specific JSON message bodies below are expected verbatim by
	// the frontend.
	_, found, err := a.DB.FetchOne(r.Context(), `
        select
         site_name
        from
         site_codes
        where
         site_code = $1
        `, siteCode)
	if err != nil {
		return err
	}
	if !found {
		err := a.DB.Exec(r.Context(),
			"insert into site_codes (site_code, site_name) values ($1, $2)",
			siteCode, sub.InputSiteName)
		if isUniqueViolation(err) {
			httpx.WriteJSON(w, http.StatusUnprocessableEntity, map[string]any{
				"message": "Your site code or site name is already in use. Please choose a unique code and name \n",
			})
			return nil
		}
		if err != nil {
			httpx.WriteJSON(w, http.StatusInternalServerError, map[string]any{
				"message": "An unexpected error occurred: \n" + err.Error(),
			})
			return nil
		}
	}

	_, found, err = a.DB.FetchOne(r.Context(), `
       select
        collection_name
       from
        collection_codes
       where
        collection_code = $1
       `, collectionCode)
	if err != nil {
		return err
	}
	if !found {
		err := a.DB.Exec(r.Context(),
			"insert into collection_codes (collection_code, collection_name) values ($1, $2)",
			collectionCode, sub.InputCollectionName)
		if isUniqueViolation(err) {
			httpx.WriteJSON(w, http.StatusUnprocessableEntity, map[string]any{
				"message": "Your collection code or collection name is already in use. Please choose a unique code and name \n",
			})
			return nil
		}
		if err != nil {
			httpx.WriteJSON(w, http.StatusInternalServerError, map[string]any{
				"message": "An unexpected error occurred: \n" + err.Error(),
			})
			return nil
		}
	}

	// Dates and ints arrive as strings; empty strings mean null. The
	// Python version pushed the raw strings through to Postgres, which
	// does the casting server-side; we do the same via ::casts.
	var baselineDate, dateShift, uidRoot any
	if sub.InputBaselineDate != nil && *sub.InputBaselineDate != "" {
		baselineDate = *sub.InputBaselineDate
	}
	if sub.InputDateShift != nil && *sub.InputDateShift != "" {
		n, err := strconv.ParseInt(*sub.InputDateShift, 10, 64)
		if err != nil {
			return httpx.NewError(http.StatusUnprocessableEntity,
				"input_date_shift must be an integer")
		}
		dateShift = n
	}
	if sub.InputUIDRoot != nil {
		uidRoot = *sub.InputUIDRoot
	}

	err = a.DB.Exec(r.Context(), `
        insert
            into submissions
            (site_code, collection_code, patient_id_prefix,
             body_part,access_type, baseline_date, date_shift, uid_root)
            values
            ($1, $2, $3, $4, $5, $6::text::timestamp, $7, $8)`,
		siteCode, collectionCode, sub.InputPatientIDPrefix,
		sub.InputBodyPart, sub.InputAccessType, baselineDate, dateShift, uidRoot)
	if isUniqueViolation(err) {
		httpx.WriteJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"message": "\n Your entry is already in use. Please choose a unique site + collection.",
		})
		return nil
	}
	if isInvalidTextRepresentation(err) {
		httpx.WriteJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"message": "Access Type must be one of: public, limited",
		})
		return nil
	}
	if err != nil {
		return err
	}

	w.WriteHeader(http.StatusCreated)
	return nil
}
