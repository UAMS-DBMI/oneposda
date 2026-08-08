package routes

import (
	"log"
	"net/http"

	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/httpx"
)

// registerVRStatus ports papi/routes/vrstatus.py.
func (a *App) registerVRStatus(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "test error, not allowed")
	})
	a.public(mux, "GET /v1/vrstatus", notAllowed)
	a.public(mux, "GET /v1/vrstatus/{$}", notAllowed)

	a.protected(mux, "GET /v1/vrstatus/find_vr_ready_to_begin_status_updates",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select
            b.visual_review_instance_id
        from
          activity_task_status a
          join visual_review_instance b
          	on b.subprocess_invocation_id = a.subprocess_invocation_id
        where
        	b.visual_review_reason = 'Activity Id: ' || a.activity_id
            and a.manual_update = true;
    `)
		})

	a.protected(mux, "GET /v1/vrstatus/get_reviewed_percentage_for_vr/{visual_review_instance_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "visual_review_instance_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        select
            ('' || processing_status::text || ' ' || ((count(*)/(select  sum(c) as t from (select count(*) as c from image_equivalence_class where visual_review_instance_id = $1 ) as sum_table)::float) * 100.0)::int || '%')::text as summary
        from
            image_equivalence_class
        where
            visual_review_instance_id = $1
        group by
            processing_status
    `, id)
		})

	a.protected(mux, "GET /v1/vrstatus/update_activity_status/{visual_review_instance_id}/{new_status}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "visual_review_instance_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        update
            activity_task_status
        set
            status_text = $2
        from
             visual_review_instance b
        where
            activity_task_status.manual_update = true
            and b.visual_review_instance_id = $1
            and b.visual_review_reason = 'Activity Id: ' || activity_task_status.activity_id
            and b.subprocess_invocation_id = activity_task_status.subprocess_invocation_id;
    `, id, pathStr(r, "new_status"))
		})

	a.protected(mux, "GET /v1/vrstatus/get_visible_bads_for_vr/{visual_review_instance_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "visual_review_instance_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        select
            'Reviewed 100% , ' || count(file_id) || ' files need to be set to Bad and hidden to continue.' as summary
        from
            image_equivalence_class a
            natural join image_equivalence_class_input_image c
            natural join ctp_file d
        where
            visual_review_instance_id = $1
        	and a.review_status <> 'Good'
    	    and ( (a.review_status = 'Bad') or a.review_status = 'Blank' or a.review_status = 'Other' or a.review_status = 'Scout' or a.review_status = 'Flagged')
    `, id)
		})

	a.protected(mux, "GET /v1/vrstatus/finish_activity_status/{visual_review_instance_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "visual_review_instance_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        update
            activity_task_status
        set
            manual_update = false
        from
             visual_review_instance b
        where
            activity_task_status.manual_update = true
            and b.visual_review_instance_id = $1
            and b.visual_review_reason = 'Activity Id: ' || activity_task_status.activity_id
            and b.subprocess_invocation_id = activity_task_status.subprocess_invocation_id;
    `, id)
		})

	a.protected(mux, "POST /v1/vrstatus/{iec}/set_status/{review_status}", a.setIECReviewStatus)
}

func (a *App) setIECReviewStatus(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	user := auth.CurrentUser(r)

	err = a.DB.Exec(r.Context(), `
            update image_equivalence_class
            set processing_status = 'Reviewed',
                review_status = $1,
                update_user = $2,
                update_date = now()
            where image_equivalence_class_id = $3
    `, pathStr(r, "review_status"), user.Username, iec)
	if err != nil {
		if isForeignKeyViolation(err) {
			return httpx.NewError(http.StatusUnprocessableEntity, "Invalid IEC supplied")
		}
		log.Printf("An error occurred: %v", err)
		return httpx.NewError(http.StatusInternalServerError, "An unexpected error occurred")
	}

	return httpx.JSON(w, map[string]any{
		"message": "IEC review status updated successfully",
	})
}
