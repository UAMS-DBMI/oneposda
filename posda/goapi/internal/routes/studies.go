package routes

import (
	"net/http"

	"tcia/posda-api/internal/httpx"
)

// registerStudies ports papi/routes/studies.py.
func (a *App) registerStudies(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "listing all studies is not allowed")
	})
	a.public(mux, "GET /v1/studies", notAllowed)
	a.public(mux, "GET /v1/studies/{$}", notAllowed)

	a.protected(mux, "GET /v1/studies/{study_instance_uid}", a.getSingleStudy)
	a.protected(mux, "GET /v1/studies/{study_instance_uid}/series", a.getStudySeries)
}

func (a *App) getSingleStudy(w http.ResponseWriter, r *http.Request) error {
	row, found, err := a.DB.FetchOne(r.Context(), `
        select
            study_date,
            study_time::text,
            count(distinct series_instance_uid) as series_count
        from file_study
        natural join file_series
        where study_instance_uid = $1
        group by
            study_date,
            study_time
    `, pathStr(r, "study_instance_uid"))
	if err != nil {
		return err
	}
	if !found {
		// Python would raise constructing StudyDetail from an empty
		// record, which surfaces as a 500.
		return httpx.ErrInternal
	}
	return httpx.JSON(w, row)
}

func (a *App) getStudySeries(w http.ResponseWriter, r *http.Request) error {
	return a.fetchJSON(w, r, `
        select distinct
            series_instance_uid
        from file_study
        natural join file_series
        where study_instance_uid = $1
    `, pathStr(r, "study_instance_uid"))
}
