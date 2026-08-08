package routes

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"

	"tcia/posda-api/internal/archive"
	"tcia/posda-api/internal/auth"
	"tcia/posda-api/internal/httpx"
)

// registerMasking ports papi/routes/masking.py.
func (a *App) registerMasking(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "not allowed")
	})
	a.public(mux, "GET /v1/masking", notAllowed)
	a.public(mux, "GET /v1/masking/{$}", notAllowed)

	a.protected(mux, "GET /v1/masking/getwork", a.getWorkForMasker)
	a.protected(mux, "POST /v1/masking/abortwork", a.abortMaskingWork)
	a.protected(mux, "POST /v1/masking/{iec}/mask", a.requestMasking)
	a.protected(mux, "GET /v1/masking/{iec}", a.getMaskingDetails)
	a.protected(mux, "POST /v1/masking/{iec}/parameters", a.updateMaskingParameters)
	a.protected(mux, "POST /v1/masking/{iec}/complete", a.markMaskingComplete)
	a.protected(mux, "POST /v1/masking/{iec}/accept", a.setMaskingStatus("accepted"))
	a.protected(mux, "POST /v1/masking/{iec}/reject", a.setMaskingStatus("rejected"))
	a.protected(mux, "POST /v1/masking/{iec}/skip", a.setMaskingStatus("skipped"))
	a.protected(mux, "POST /v1/masking/{iec}/nonmaskable", a.setMaskingStatus("nonmaskable"))
	a.protected(mux, "GET /v1/masking/visualreview/{visual_review_instance_id}/next-for-review",
		a.nextMaskingIEC("process-complete"))
	a.protected(mux, "GET /v1/masking/visualreview/{visual_review_instance_id}/next",
		a.nextMaskingIEC("created"))
	a.protected(mux, "GET /v1/masking/visualreview/{visual_review_instance_id}", a.getMaskingForVR)
	a.protected(mux, "GET /v1/masking/visualreview/{visual_review_instance_id}/values", a.getMaskingValues)
	a.protected(mux, "POST /v1/masking/visualreview/{visual_review_instance_id}/filter", a.getMaskingFiltered)
	a.protected(mux, "GET /v1/masking/{iec}/reviewfiles", a.getMaskingReviewFiles)
	a.protected(mux, "GET /v1/masking/{iec}/reviewfiles/download", a.downloadMaskingReviewFiles)
}

func (a *App) getWorkForMasker(w http.ResponseWriter, r *http.Request) error {
	row, found, err := a.DB.FetchOne(r.Context(), `
        update masking
        set masking_status = 'in-process'
        where image_equivalence_class_id = (
            select image_equivalence_class_id
            from masking
            where masking_status = 'ready-to-process'
            limit 1
            for update skip locked
        )
        returning image_equivalence_class_id
    `)
	if err != nil {
		return err
	}
	if !found {
		return httpx.NewError(http.StatusNotFound, "Not Found")
	}
	return httpx.JSON(w, row)
}

func (a *App) abortMaskingWork(w http.ResponseWriter, r *http.Request) error {
	iec, err := queryInt(r, "iec", 0)
	if err != nil {
		return err
	}
	if !r.URL.Query().Has("iec") {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"query parameter \"iec\" is required")
	}
	err = a.DB.Exec(r.Context(), `
        update masking
        set masking_status = 'ready-to-process'
        where image_equivalence_class_id = $1
          and masking_status = 'in-process'
    `, iec)
	if err != nil {
		return err
	}
	return httpx.JSON(w, nil)
}

func (a *App) requestMasking(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	user := auth.CurrentUser(r)

	row, found, err := a.DB.FetchOne(r.Context(), `
        insert into masking
        (image_equivalence_class_id)
        values
        ($1)
        returning masking.*
    `, iec)
	if err != nil {
		if isUniqueViolation(err) {
			return httpx.NewError(http.StatusConflict, "Already exists")
		}
		if isForeignKeyViolation(err) {
			return httpx.NewError(http.StatusUnprocessableEntity, "Invalid IEC supplied")
		}
		return err
	}

	if err := a.insertMaskingHistory(r, iec, "created", user.UserID); err != nil {
		return err
	}
	if !found {
		return httpx.JSON(w, []any{})
	}
	return httpx.JSON(w, row)
}

func (a *App) insertMaskingHistory(r *http.Request, iec int64, status string, userID int64) error {
	return a.DB.Exec(r.Context(), `
        insert into masking_history
        values
        ($1, $2, now(), $3)
    `, iec, status, userID)
}

func (a *App) getMaskingDetails(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}

	row, _, err := a.DB.FetchOne(r.Context(), `
        with input_image as (
            select distinct image_equivalence_class_id, site_id
            from masking
            natural join image_equivalence_class_input_image
            natural join ctp_file
        ), uid_root as (
            select input_image.*, uid_root
            from input_image
            join submissions on submissions.site_code || submissions.collection_code = input_image.site_id
        )

        select *
        from masking
        natural left join uid_root
        where image_equivalence_class_id = $1
    `, iec)
	if err != nil {
		return err
	}

	history, err := a.DB.Fetch(r.Context(), `
        select
            h.new_status,
            h.when_changed,
            u.user_name as who_changed
        from masking_history h
        join auth.users u on u.user_id = h.who_changed
        where image_equivalence_class_id = $1
    `, iec)
	if err != nil {
		return err
	}

	// Missing rows still produce {"history": [...]}, matching
	// dict(fetch_one_result) on an empty result.
	row.Set("history", history)
	return httpx.JSON(w, row)
}

func (a *App) updateMaskingParameters(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	user := auth.CurrentUser(r)

	params := struct {
		LR       *int64  `json:"LR"`
		PA       *int64  `json:"PA"`
		IS       *int64  `json:"IS"`
		Width    *int64  `json:"width"`
		Height   *int64  `json:"height"`
		Depth    *int64  `json:"depth"`
		Fill     *int64  `json:"fill"`
		Noise    *int64  `json:"noise"`
		Form     *string `json:"form"`
		Function *string `json:"function"`
	}{}
	if err := decodeJSONBody(r, &params); err != nil {
		return err
	}
	for name, v := range map[string]*int64{
		"LR": params.LR, "PA": params.PA, "IS": params.IS,
		"width": params.Width, "height": params.Height, "depth": params.Depth,
	} {
		if v == nil {
			return httpx.NewError(http.StatusUnprocessableEntity,
				fmt.Sprintf("body field %q is required", name))
		}
	}
	if params.Form == nil {
		s := "cylinder"
		params.Form = &s
	}
	if params.Function == nil {
		s := "mask"
		params.Function = &s
	}

	// Serialized the same way pydantic's model_dump_json does, so the
	// stored parameters keep the same field order and null handling.
	jsonStr, err := httpx.MarshalJSON(orderedParams(params.LR, params.PA, params.IS,
		params.Width, params.Height, params.Depth, params.Fill, params.Noise,
		params.Form, params.Function))
	if err != nil {
		return err
	}

	const newStatus = "ready-to-process"
	err = a.DB.Exec(r.Context(), `
        INSERT INTO masking (image_equivalence_class_id, masking_status, masking_parameters)
        VALUES ($1, $2, $3)
        ON CONFLICT (image_equivalence_class_id)
        DO UPDATE SET
            masking_status = EXCLUDED.masking_status,
            masking_parameters = EXCLUDED.masking_parameters
    `, iec, newStatus, string(jsonStr))
	if err != nil {
		if isForeignKeyViolation(err) {
			return httpx.NewError(http.StatusUnprocessableEntity, "Invalid IEC supplied")
		}
		return err
	}

	if err := a.insertMaskingHistory(r, iec, newStatus, user.UserID); err != nil {
		return err
	}

	// Echo the parameters back, like the Python version returns `item`.
	var echo maskingParamsJSON
	if err := json.Unmarshal(jsonStr, &echo); err != nil {
		return err
	}
	return httpx.JSON(w, echo)
}

func (a *App) markMaskingComplete(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	user := auth.CurrentUser(r)

	var body struct {
		ImportEventID *int64 `json:"import_event_id"`
		ExitCode      *int64 `json:"exit_code"`
	}
	if err := decodeJSONBody(r, &body); err != nil {
		return err
	}
	if body.ImportEventID == nil || body.ExitCode == nil {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"import_event_id and exit_code are required")
	}

	newStatus := "process-complete"
	importEventID := body.ImportEventID
	if *body.ExitCode != 0 {
		newStatus = "errored"
		importEventID = nil
	}

	err = a.DB.Exec(r.Context(), `
        update masking
        set import_event_id = $1,
            masking_exit_code = $2,
            masking_status = $3
        where image_equivalence_class_id = $4
    `, importEventID, *body.ExitCode, newStatus, iec)
	if err != nil {
		if isForeignKeyViolation(err) {
			return httpx.NewError(http.StatusUnprocessableEntity, "Invalid IEC supplied")
		}
		return err
	}

	if err := a.insertMaskingHistory(r, iec, newStatus, user.UserID); err != nil {
		return err
	}

	return httpx.JSON(w, map[string]any{
		"import_event_id": body.ImportEventID,
		"exit_code":       body.ExitCode,
	})
}

// setMaskingStatus covers the accept/reject/skip/nonmaskable family:
// update the status, record history, return null (the Python handlers
// have no return value).
func (a *App) setMaskingStatus(newStatus string) httpx.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		iec, err := pathInt(r, "iec")
		if err != nil {
			return err
		}
		user := auth.CurrentUser(r)

		err = a.DB.Exec(r.Context(), `
            update masking
            set masking_status = $1
            where image_equivalence_class_id = $2
        `, newStatus, iec)
		if err != nil {
			if isForeignKeyViolation(err) {
				return httpx.NewError(http.StatusUnprocessableEntity, "Invalid IEC supplied")
			}
			return err
		}
		if err := a.insertMaskingHistory(r, iec, newStatus, user.UserID); err != nil {
			return err
		}
		return httpx.JSON(w, nil)
	}
}

// nextMaskingIEC picks a random IEC in the VR with the given masking
// status (used to hand out work to curators).
func (a *App) nextMaskingIEC(status string) httpx.HandlerFunc {
	// The two Python queries differ only in the required status (and a
	// join to file_import in the review variant, which does not change
	// the picked id).
	sql := `
        with all_ready_iecs as (
            select
                image_equivalence_class_id
            from
                image_equivalence_class
                natural join masking
            where
                visual_review_instance_id = $1
                and masking_status = $2
        )

        select *
        from all_ready_iecs
        order by random()
        limit 1
    `
	reviewSQL := `
        with all_ready_for_review as (
            select
                image_equivalence_class_id
            from
                image_equivalence_class
                natural join masking
                natural join file_import
            where
                visual_review_instance_id = $1
                and masking_status = $2
        )

        select *
        from all_ready_for_review
        order by random()
        limit 1
    `
	return func(w http.ResponseWriter, r *http.Request) error {
		vr, err := pathInt(r, "visual_review_instance_id")
		if err != nil {
			return err
		}
		query := sql
		if status == "process-complete" {
			query = reviewSQL
		}
		row, found, err := a.DB.FetchOne(r.Context(), query, vr, status)
		if err != nil {
			return err
		}
		if !found {
			return errNoRecords
		}
		// Python returns record[0]: just the id.
		return httpx.JSON(w, row.Values()[0])
	}
}

func (a *App) getMaskingForVR(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "visual_review_instance_id")
	if err != nil {
		return err
	}
	if queryBool(r, "awaiting_review", false) {
		return a.fetchFirstColumn(w, r, `
        select
            image_equivalence_class_id
        from
            image_equivalence_class
            natural join masking
        where
            visual_review_instance_id = $1
            and masking_status = 'process-complete'
    `, vr)
	}
	return a.fetchFirstColumn(w, r, `
        select
            image_equivalence_class_id
        from
            image_equivalence_class
            natural join masking
        where
            visual_review_instance_id = $1
            and masking_status in ('created', 'rejected')
    `, vr)
}

func (a *App) getMaskingValues(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "visual_review_instance_id")
	if err != nil {
		return err
	}

	dicomFileTypes, err := a.DB.Fetch(r.Context(), `
        with iecs as (
            select image_equivalence_class_id
            from image_equivalence_class
            natural join masking
            where visual_review_instance_id = $1
        )
        select
            (
                select dicom_file_type
                from image_equivalence_class_input_image
                natural join dicom_file
                where image_equivalence_class_input_image.image_equivalence_class_id = iecs.image_equivalence_class_id
                limit 1
            ),
            count(*)
        from iecs
        group by 1
    `, vr)
	if err != nil {
		return err
	}

	maskingStatuses, err := a.DB.Fetch(r.Context(), `
        select
            masking_status,
            count(*) as count
        from
            image_equivalence_class
            natural join masking
        where
            visual_review_instance_id = $1
        group by 1
    `, vr)
	if err != nil {
		return err
	}

	if len(dicomFileTypes) == 0 && len(maskingStatuses) == 0 {
		exists, err := a.vrExists(r, vr)
		if err != nil {
			return err
		}
		if !exists {
			return httpx.NewError(http.StatusNotFound, "invalid visual review id")
		}
	}

	return httpx.JSON(w, map[string]any{
		"dicom_file_types": dicomFileTypes,
		"masking_statuses": maskingStatuses,
	})
}

func (a *App) getMaskingFiltered(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "visual_review_instance_id")
	if err != nil {
		return err
	}
	var params struct {
		DicomFileType filterParam `json:"dicom_file_type"`
		MaskingStatus filterParam `json:"masking_status"`
	}
	if err := decodeJSONBody(r, &params); err != nil {
		return err
	}

	query := `
        with iecs as (
            select
            image_equivalence_class_id,
            masking_status,
                (
                    /*
                            All files in an IEC must always be of the same dicom_file_type,
                            so we can just select the first one here for speed
                    */
                    select dicom_file_type
                    from image_equivalence_class_input_image
                    natural join dicom_file
                    where image_equivalence_class_input_image.image_equivalence_class_id =
                            image_equivalence_class.image_equivalence_class_id
                    limit 1
                ) dicom_file_type
            from image_equivalence_class
            natural join masking
            where visual_review_instance_id = $1
        )

        select image_equivalence_class_id
        from iecs
        where 1 = 1
    `
	args := []any{vr}
	params.DicomFileType.appendFilter("dicom_file_type", &query, &args)
	params.MaskingStatus.appendFilter("masking_status", &query, &args)
	query += "order by 1"

	rows, err := a.DB.Fetch(r.Context(), query, args...)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		exists, err := a.vrExists(r, vr)
		if err != nil {
			return err
		}
		if !exists {
			return httpx.NewError(http.StatusNotFound, "invalid visual review id")
		}
	}
	return httpx.JSON(w, firstColumn(rows))
}

func (a *App) getMaskingReviewFiles(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	rows, err := a.DB.Fetch(r.Context(), `
        select distinct
            file_id,
            file_storage_root_id || '/' || file_location.rel_path as path,
            image_type,
            coalesce(number_of_frames, 1) as frame_count,
            iop,
            ipp
        from
            masking
            natural join file_import
            natural join dicom_file
            left join file_location using (file_id)
            natural left join file_image
            natural left join image
            natural left join image_geometry
        where
            image_equivalence_class_id = $1
    `, iec)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		return errNoRecords
	}

	sorted, _, err := iecFrameList(rows)
	if err != nil {
		return err
	}

	// The consistency guess is deliberately ignored (see the TODO in
	// the Python source): the UI expects volumetric=true.
	return httpx.JSON(w, map[string]any{
		"volumetric": true,
		"frames":     frameListJSON(sorted),
	})
}

func (a *App) downloadMaskingReviewFiles(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	rows, err := a.DB.Fetch(r.Context(), `
        select
            root_path || '/' || file_location.rel_path as file
        from
            masking
            natural join file_import
            join file_location using(file_id)
            natural join file_storage_root
        where
            image_equivalence_class_id = $1
    `, iec)
	if err != nil {
		return err
	}
	files := make([]string, 0, len(rows))
	for _, row := range rows {
		files = append(files, row.GetString("file"))
	}
	return archive.StreamZip(w, files, strconv.FormatInt(iec, 10)+".zip")
}

// orderedParams builds the masking parameter JSON with the same field
// order as the pydantic model.
func orderedParams(lr, pa, is, width, height, depth, fill, noise *int64, form, function *string) any {
	return maskingParamsJSON{lr, pa, is, width, height, depth, fill, noise, form, function}
}

type maskingParamsJSON struct {
	LR       *int64  `json:"LR"`
	PA       *int64  `json:"PA"`
	IS       *int64  `json:"IS"`
	Width    *int64  `json:"width"`
	Height   *int64  `json:"height"`
	Depth    *int64  `json:"depth"`
	Fill     *int64  `json:"fill"`
	Noise    *int64  `json:"noise"`
	Form     *string `json:"form"`
	Function *string `json:"function"`
}
