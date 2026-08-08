package routes

import (
	"net/http"
)

// registerCollections ports papi/routes/collections.py.
func (a *App) registerCollections(mux *http.ServeMux) {
	list := a.Auth.Middleware(a.getAllCollections)
	a.public(mux, "GET /v1/collections", list)
	a.public(mux, "GET /v1/collections/{$}", list)

	a.protected(mux, "GET /v1/collections/{collection_name}/{site_name}", a.getCollectionInfo)
	a.protected(mux, "GET /v1/collections/{collection_name}/{site_name}/patients", a.getAllPatients)
	a.protected(mux, "GET /v1/collections/{collection_name}/{site_name}/patients/{patient_id}", a.getSinglePatient)
	a.protected(mux, "GET /v1/collections/{collection_name}/{site_name}/patients/{patient_id}/studies", a.getPatientStudies)
}

func (a *App) getAllCollections(w http.ResponseWriter, r *http.Request) error {
	const base = `
        select
            project_name as collection,
            site_name as site,
            count(file_id) as file_count
        from ctp_file
        %s
        group by project_name, site_name
    `

	// If both filters are set, site is ignored (same as Python).
	if collection := queryStr(r, "collection", ""); collection != "" {
		return a.fetchJSON(w, r,
			"select project_name as collection, site_name as site, count(file_id) as file_count "+
				"from ctp_file where project_name = $1 group by project_name, site_name",
			collection)
	}
	if site := queryStr(r, "site", ""); site != "" {
		return a.fetchJSON(w, r,
			"select project_name as collection, site_name as site, count(file_id) as file_count "+
				"from ctp_file where site_name = $1 group by project_name, site_name",
			site)
	}
	return a.fetchJSON(w, r,
		"select project_name as collection, site_name as site, count(file_id) as file_count "+
			"from ctp_file group by project_name, site_name")
}

func (a *App) getCollectionInfo(w http.ResponseWriter, r *http.Request) error {
	return a.fetchOneJSON(w, r, `
        select
            project_name as collection,
            site_name as site,
            count(file_id) as file_count,
            count(distinct patient_name) as patient_count
        from ctp_file
        natural join file_patient
        where project_name = $1
          and site_name = $2
        group by
            project_name, site_name
    `, pathStr(r, "collection_name"), pathStr(r, "site_name"))
}

func (a *App) getAllPatients(w http.ResponseWriter, r *http.Request) error {
	return a.fetchJSON(w, r, `
        select distinct
            patient_name as patient
        from ctp_file
        natural join file_patient
        where project_name = $1
          and site_name = $2
    `, pathStr(r, "collection_name"), pathStr(r, "site_name"))
}

func (a *App) getSinglePatient(w http.ResponseWriter, r *http.Request) error {
	return a.fetchOneJSON(w, r, `
        select
            patient_name as patient,
            max(patient_id) as patient_id,
            max(sex) as patient_sex,
            max(ethnic_group) as patient_ethnic_group,
            array_agg(distinct comments) as comments,
            count(file_id) as file_count,
            count(distinct study_instance_uid) as study_count
        from ctp_file
        natural join file_patient
        natural join file_study
        where project_name = $1
          and site_name = $2
          and patient_name = $3
        group by patient_name
    `, pathStr(r, "collection_name"), pathStr(r, "site_name"), pathStr(r, "patient_id"))
}

func (a *App) getPatientStudies(w http.ResponseWriter, r *http.Request) error {
	return a.fetchJSON(w, r, `
        select distinct
            project_name as collection,
            site_name as site,
            patient_name as patient,
            study_instance_uid
        from ctp_file
        natural join file_patient
        natural join file_study
        where project_name = $1
          and site_name = $2
          and patient_name = $3
    `, pathStr(r, "collection_name"), pathStr(r, "site_name"), pathStr(r, "patient_id"))
}
