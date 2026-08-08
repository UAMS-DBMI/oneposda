package routes

import (
	"net/http"

	"tcia/posda-api/internal/httpx"
)

// registerDeface ports papi/routes/deface.py.
func (a *App) registerDeface(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/deface/{defacing_id}", a.getDefacing)
	a.protected(mux, "POST /v1/deface/{defacing_id}/complete", a.defacingComplete(true))
	a.protected(mux, "POST /v1/deface/{defacing_id}/error", a.defacingComplete(false))
}

func (a *App) getDefacing(w http.ResponseWriter, r *http.Request) error {
	id, err := pathInt(r, "defacing_id")
	if err != nil {
		return err
	}
	row, found, err := a.DB.FetchOne(r.Context(), `
        select *
        from
            file_nifti_defacing
        where
            file_nifti_defacing_id = $1
    `, id)
	if err != nil {
		return err
	}
	if !found {
		return httpx.NewError(http.StatusNotFound, "no such defacing_id")
	}
	return httpx.JSON(w, row)
}

type defaceResult struct {
	NiftiFileID           *int64  `json:"nifti_file_id"`
	ThreeDRenderedFace    *int64  `json:"three_d_rendered_face"`
	ThreeDRenderedFaceBox *int64  `json:"three_d_rendered_face_box"`
	ThreeDRenderedDefaced *int64  `json:"three_d_rendered_defaced"`
	ErrorCode             *string `json:"error_code"`
}

func (a *App) defacingComplete(success bool) httpx.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		id, err := pathInt(r, "defacing_id")
		if err != nil {
			return err
		}
		var body defaceResult
		if err := decodeJSONBody(r, &body); err != nil {
			return err
		}

		err = a.DB.Exec(r.Context(), `
        update
            file_nifti_defacing
        set
            to_nifti_file = $2,
            three_d_rendered_face = $3,
            three_d_rendered_face_box = $4,
            three_d_rendered_defaced = $5,
            error_code = $6,
            success = `+successLiteral(success)+`,
            completed_time = now()
        where
            file_nifti_defacing_id = $1
        `,
			id,
			body.NiftiFileID,
			body.ThreeDRenderedFace,
			body.ThreeDRenderedFaceBox,
			body.ThreeDRenderedDefaced,
			body.ErrorCode,
		)
		if err != nil {
			return err
		}
		return httpx.JSON(w, map[string]any{"status": "success"})
	}
}

func successLiteral(success bool) string {
	if success {
		return "true"
	}
	return "false"
}
