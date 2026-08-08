package routes

import (
	"fmt"
	"net/http"
	"path"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/httpx"
)

// registerNifti ports papi/routes/nifti.py.
func (a *App) registerNifti(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/nifti/{nifti_id}", a.getNiftiDetails)
	a.protected(mux, "POST /v1/nifti/{nifti_id}/set_status/{review_status}", a.setNiftiStatus)
	a.protected(mux, "GET /v1/nifti/visualreview/{nifti_visual_review_instance_id}", a.getNiftiVisualReview)
}

func (a *App) getNiftiDetails(w http.ResponseWriter, r *http.Request) error {
	niftiID, err := pathInt(r, "nifti_id")
	if err != nil {
		return err
	}
	row, found, err := a.DB.FetchOne(r.Context(), `
        select fn.file_id,
               fi.file_name,
               fsr.root_path,
               fl.rel_path,
               fn.is_zipped
        from file_nifti fn
        natural join file_location fl
        natural join file_storage_root fsr
        left join file_import fi
        on fn.file_id = fi.file_id
        and fi.import_event_id = (
            select max(import_event_id)
            from file_import fi_sub
            where fi_sub.file_id = fn.file_id)
        where fn.file_id = $1
    `, niftiID)
	if err != nil {
		return err
	}
	if !found {
		return httpx.JSON(w, map[string]any{})
	}

	importPath, importName := path.Split(row.GetString("file_name"))
	if importPath != "" {
		importPath = importPath[:len(importPath)-1] // os.path.split keeps no trailing slash
	}
	row.Set("import_path", importPath)
	row.Set("import_name", importName)
	row.Set("download_path", fmt.Sprintf("/papi/v1/files/%d/data", niftiID))
	row.Set("posda_path", fmt.Sprintf("%s/%s",
		row.GetString("root_path"), row.GetString("rel_path")))

	return httpx.JSON(w, row)
}

func (a *App) setNiftiStatus(w http.ResponseWriter, r *http.Request) error {
	niftiID, err := pathInt(r, "nifti_id")
	if err != nil {
		return err
	}
	user := auth.CurrentUser(r)

	err = a.DB.Exec(r.Context(), `
        insert into nifti_visual_review_status (nifti_file_id, review_status, reviewing_user, review_time)
        values ($1, $2, $3, now())
        on conflict (nifti_file_id)
        do update set
            review_status = EXCLUDED.review_status,
            reviewing_user = EXCLUDED.reviewing_user,
            review_time = now();
    `, niftiID, pathStr(r, "review_status"), user.Username)
	if err != nil {
		if isForeignKeyViolation(err) {
			return httpx.NewError(http.StatusUnprocessableEntity, "Invalid File ID supplied")
		}
		return httpx.NewError(http.StatusInternalServerError, "An unexpected error occurred")
	}
	return httpx.JSON(w, map[string]any{
		"message": "Nifti review status updated successfully",
	})
}

func (a *App) getNiftiVisualReview(w http.ResponseWriter, r *http.Request) error {
	id, err := pathInt(r, "nifti_visual_review_instance_id")
	if err != nil {
		return err
	}
	return a.fetchFirstColumn(w, r, `
        select
            nifti_file_id
        from
            nifti_visual_review_files
                natural left join nifti_visual_review_status
        where
            nifti_visual_review_instance_id = $1
            and nifti_visual_review_status.nifti_file_id is null
        order by 1
    `, id)
}
