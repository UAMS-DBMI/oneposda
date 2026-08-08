package routes

import (
	"fmt"
	"net/http"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/dicom"
	"tcia/posda-api/internal/httpx"
)

// registerIECs ports papi/routes/iecs.py.
func (a *App) registerIECs(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "listing all iecs is not allowed")
	})
	a.public(mux, "GET /v1/iecs", notAllowed)
	a.public(mux, "GET /v1/iecs/{$}", notAllowed)

	a.protected(mux, "GET /v1/iecs/{iec}", a.getIECDetails)
	a.protected(mux, "GET /v1/iecs/{iec}/files", a.getIECFiles)
	a.protected(mux, "GET /v1/iecs/{iec}/frames", a.getIECFrames)
	a.protected(mux, "GET /v1/iecs/{iec}/info", a.getIECInfo)
	a.protected(mux, "GET /v1/iecs/{iec}/other_iecs_in_for", a.getIECsSharingFOR)
}

func (a *App) getIECDetails(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	// Python returns db.fetch here, so the response is a list.
	return a.fetchJSON(w, r, `
        select *
        from image_equivalence_class
        where image_equivalence_class_id = $1
    `, iec)
}

func (a *App) getIECFiles(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	rows, err := a.DB.Fetch(r.Context(), `
    select
        file_id
    from
        image_equivalence_class_input_image
        natural join file_sop_common
    where
        image_equivalence_class_id = $1
    order by
        -- sometimes instance_number is empty string or null
        case instance_number
            when '' then '0'
            when null then '0'
            else instance_number
        end::int
    `, iec)
	if err != nil {
		return err
	}
	return httpx.JSON(w, map[string]any{"file_ids": firstColumn(rows)})
}

// iecFrameList runs a frame-listing query and applies the volumetric
// consistency check, returning the sorted files.
func iecFrameList(rows []db.Row) ([]dicom.ImageFile, bool, error) {
	files := make([]dicom.ImageFile, 0, len(rows))
	for _, row := range rows {
		iop, _ := row.Get("iop").(string)
		ipp, _ := row.Get("ipp").(string)
		imageType, _ := row.Get("image_type").(string)
		f, err := dicom.NewImageFile(
			row.GetInt("file_id"),
			row.GetString("path"),
			imageType,
			row.GetInt("frame_count"),
			iop,
			ipp,
		)
		if err != nil {
			return nil, false, err
		}
		files = append(files, f)
	}
	sorted, volumetric := dicom.Consistent(files)
	return sorted, volumetric, nil
}

func frameListJSON(files []dicom.ImageFile) []any {
	out := make([]any, 0, len(files))
	for _, f := range files {
		out = append(out, map[string]any{
			"file_id":       f.FileID,
			"path":          f.Path,
			"num_of_frames": f.FrameCount,
		})
	}
	return out
}

const iecFramesQuery = `
    select distinct
        file_id,
        file_storage_root_id || '/' || rel_path as path,
        image_type,
        coalesce(number_of_frames, 1) as frame_count,
        iop,
        ipp
    from
        image_equivalence_class_input_image
        natural join file_location
        natural left join file_image
        natural left join image
        natural left join image_geometry
    where
        image_equivalence_class_id = $1
`

func (a *App) getIECFrames(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	includeFrames := queryBool(r, "include_frames", true)

	rows, err := a.DB.Fetch(r.Context(), iecFramesQuery, iec)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		return errNoRecords
	}

	sorted, volumetric, err := iecFrameList(rows)
	if err != nil {
		return err
	}

	if !includeFrames {
		return httpx.JSON(w, map[string]any{"volumetric": volumetric})
	}
	return httpx.JSON(w, map[string]any{
		"volumetric": volumetric,
		"frames":     frameListJSON(sorted),
	})
}

func (a *App) getIECInfo(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}

	// Volumetric guess, same as the /frames endpoint (404 when the IEC
	// has no files at all).
	frameRows, err := a.DB.Fetch(r.Context(), iecFramesQuery, iec)
	if err != nil {
		return err
	}
	if len(frameRows) == 0 {
		return errNoRecords
	}
	_, volumetric, err := iecFrameList(frameRows)
	if err != nil {
		return err
	}

	row, found, err := a.DB.FetchOne(r.Context(), `
        select
            visual_review_instance_id,
            image_equivalence_class_id,
            series_instance_uid,
            equivalence_class_number,
            processing_status,
            review_status,
            update_user,
            to_char(update_date, 'YYYY-MM-DD HH:MI:SS AM') as update_date,
            (select count(file_id)
             from image_equivalence_class_input_image i
             where i.image_equivalence_class_id =
                   image_equivalence_class.image_equivalence_class_id) as file_count,
            (select body_part_examined
             from file_series
             where file_series.series_instance_uid = image_equivalence_class.series_instance_uid limit 1) as body_part_examined,
            (select modality
             from file_series
             where file_series.series_instance_uid = image_equivalence_class.series_instance_uid limit 1) as modality,
            (select patient_id
             from file_patient
             natural join file_series
             where file_series.series_instance_uid = image_equivalence_class.series_instance_uid limit 1) as patient_id,
            (select series_description
             from image_equivalence_class_input_image
             natural join file_series
             where image_equivalence_class_input_image.image_equivalence_class_id = image_equivalence_class.image_equivalence_class_id
             limit 1
            ) as series_description,
            (select for_uid
             from image_equivalence_class_input_image
             natural join file_for
             where image_equivalence_class_input_image.image_equivalence_class_id = image_equivalence_class.image_equivalence_class_id
             limit 1
            ) as frame_of_reference_uid
        from image_equivalence_class
        where image_equivalence_class_id = $1
    `, iec)
	if err != nil {
		return err
	}
	if !found {
		// dict([]) in Python produces an empty object response.
		return httpx.JSON(w, map[string]any{})
	}

	row.Set("download_path", fmt.Sprintf("/papi/v1/files/iec/%d", iec))
	row.Set("download_name", fmt.Sprintf("iec_%d.zip", iec))
	row.Set("volumetric", volumetric)
	return httpx.JSON(w, row)
}

func (a *App) getIECsSharingFOR(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	return a.fetchJSON(w, r, `
        with input_for as (
            select distinct for_uid, visual_review_instance_id
            from image_equivalence_class_input_image
            natural join image_equivalence_class
            natural join file_for
            where image_equivalence_class_id = $1
            limit 1
        ), candidate_files as (
            select file_id, image_equivalence_class_id
            from image_equivalence_class
            natural join image_equivalence_class_input_image
            where visual_review_instance_id = (select visual_review_instance_id from input_for)
        )
        select image_equivalence_class_id,
               series_instance_uid,
               series_description,
               modality,
               count(file_id) as file_count
        from candidate_files
        natural join file_for
        natural join file_series
        where for_uid = (select for_uid from input_for)
        and image_equivalence_class_id != $1
        group by 1, 2, 3, 4
        order by file_count desc
    `, iec)
}
