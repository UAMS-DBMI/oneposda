package routes

import (
	"net/http"
	"strconv"

	"tcia/posda-api/internal/httpx"
)

// registerVisualReviews ports papi/routes/visualreviews.py.
func (a *App) registerVisualReviews(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "listing all VRs is not allowed")
	})
	a.public(mux, "GET /v1/visualreviews", notAllowed)
	a.public(mux, "GET /v1/visualreviews/{$}", notAllowed)

	a.protected(mux, "GET /v1/visualreviews/{vr}", a.getVRDetails)
	a.protected(mux, "GET /v1/visualreviews/{vr}/iecs", a.getVRIECs)
	a.protected(mux, "GET /v1/visualreviews/{vr}/values", a.getVRValues)
	a.protected(mux, "POST /v1/visualreviews/{vr}/filter", a.getVRFiltered)
}

func (a *App) getVRDetails(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "vr")
	if err != nil {
		return err
	}
	return a.fetchJSON(w, r, `
        select *
        from visual_review_instance
        where visual_review_instance_id = $1
    `, vr)
}

func (a *App) getVRIECs(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "vr")
	if err != nil {
		return err
	}
	return a.fetchFirstColumn(w, r, `
        select
            image_equivalence_class_id
        from
            image_equivalence_class
        where
            visual_review_instance_id = $1
        order by 1
    `, vr)
}

// vrExists double-checks a visual_review_instance_id; used when queries
// come back empty to distinguish "no data" from "bad id".
func (a *App) vrExists(r *http.Request, vr int64) (bool, error) {
	rows, err := a.DB.Fetch(r.Context(), `
        select visual_review_instance_id
        from visual_review_instance
        where visual_review_instance_id = $1
    `, vr)
	if err != nil {
		return false, err
	}
	return len(rows) > 0, nil
}

func (a *App) getVRValues(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "vr")
	if err != nil {
		return err
	}

	dicomFileTypes, err := a.DB.Fetch(r.Context(), `
        with iecs as (
            select image_equivalence_class_id, review_status, processing_status
            from image_equivalence_class
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

	reviewStatuses, err := a.DB.Fetch(r.Context(), `
        select
            review_status,
            count(*) as count
        from image_equivalence_class
        where visual_review_instance_id = $1
        group by 1
    `, vr)
	if err != nil {
		return err
	}

	processingStatuses, err := a.DB.Fetch(r.Context(), `
        select
            processing_status,
            count(*) as count
        from image_equivalence_class
        where visual_review_instance_id = $1
        group by 1
    `, vr)
	if err != nil {
		return err
	}

	if len(dicomFileTypes) == 0 && len(reviewStatuses) == 0 && len(processingStatuses) == 0 {
		exists, err := a.vrExists(r, vr)
		if err != nil {
			return err
		}
		if !exists {
			return httpx.NewError(http.StatusNotFound, "invalid visual review id")
		}
	}

	return httpx.JSON(w, map[string]any{
		"dicom_file_types":    dicomFileTypes,
		"review_statuses":     reviewStatuses,
		"processing_statuses": processingStatuses,
	})
}

// vrFilterParams are shared by the visualreviews and masking filter
// endpoints: "*" means no filtering, null means "is null".
type filterParam struct {
	set   bool
	value *string
}

func (p *filterParam) UnmarshalJSON(data []byte) error {
	p.set = true
	if string(data) == "null" {
		p.value = nil
		return nil
	}
	s := ""
	if len(data) >= 2 && data[0] == '"' {
		s = string(data[1 : len(data)-1])
	} else {
		s = string(data)
	}
	p.value = &s
	return nil
}

// appendFilter extends query/args for one filter parameter following
// the Python logic: absent or "*" means skip, null means IS NULL.
func (p filterParam) appendFilter(column string, query *string, args *[]any) {
	if !p.set {
		return // defaults to "*", meaning no filter
	}
	if p.value != nil && *p.value == "*" {
		return
	}
	if p.value == nil {
		*query += "and " + column + " is null\n"
		return
	}
	*args = append(*args, *p.value)
	*query += "and " + column + " = $" + strconv.Itoa(len(*args)) + "\n"
}

func (a *App) getVRFiltered(w http.ResponseWriter, r *http.Request) error {
	vr, err := pathInt(r, "vr")
	if err != nil {
		return err
	}
	var params struct {
		DicomFileType    filterParam `json:"dicom_file_type"`
		ProcessingStatus filterParam `json:"processing_status"`
		ReviewStatus     filterParam `json:"review_status"`
	}
	if err := decodeJSONBody(r, &params); err != nil {
		return err
	}

	query := `
        with iecs as (
            select
            image_equivalence_class_id,
            review_status,
            processing_status,
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
            where visual_review_instance_id = $1
        )

        select image_equivalence_class_id
        from iecs
        where 1 = 1
    `
	args := []any{vr}
	params.DicomFileType.appendFilter("dicom_file_type", &query, &args)
	params.ProcessingStatus.appendFilter("processing_status", &query, &args)
	params.ReviewStatus.appendFilter("review_status", &query, &args)
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
