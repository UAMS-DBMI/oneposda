package routes

import (
	"log"
	"net/http"
	"os"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/dicom"
	"tcia/posda-api/internal/httpx"
)

// registerROIs ports papi/routes/rois.py.
func (a *App) registerROIs(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "test error, not allowed")
	})
	a.public(mux, "GET /v1/rois", notAllowed)
	a.public(mux, "GET /v1/rois/{$}", notAllowed)

	a.protected(mux, "GET /v1/rois/series/{series_instance_uid}", a.getROIsForSeries)
	a.protected(mux, "GET /v1/rois/file/{file_id}/series", a.getSeriesROIsFromFile)
	a.protected(mux, "GET /v1/rois/sop/{sop_instance_uid}", a.getContoursForSOP)
	a.protected(mux, "GET /v1/rois/file/{file_id}", a.getContoursForFile)
}

func (a *App) roisForSeries(w http.ResponseWriter, r *http.Request, uid string) error {
	rows, err := a.DB.Fetch(r.Context(), `
        select
            roi_num,
            roi_name as name,
            roi_color as color,
            array_agg(file_sop_common.file_id) as file_ids
        from file_series
        natural join file_sop_common
        join file_roi_image_linkage
            on linked_sop_instance_uid = sop_instance_uid
        natural join roi
        where series_instance_uid = $1
        group by roi_num, roi_name, roi_color
        order by roi_num
    `, uid)
	if err != nil {
		return err
	}

	out := make([]any, 0, len(rows))
	for _, row := range rows {
		color, _ := row.Get("color").(string)
		out = append(out, map[string]any{
			"roi_num":  row.Get("roi_num"),
			"name":     row.Get("name"),
			"color":    dicom.FormatColor(color),
			"file_ids": row.Get("file_ids"),
		})
	}
	return httpx.JSON(w, out)
}

func (a *App) getROIsForSeries(w http.ResponseWriter, r *http.Request) error {
	return a.roisForSeries(w, r, pathStr(r, "series_instance_uid"))
}

func (a *App) getSeriesROIsFromFile(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	row, found, err := a.DB.FetchOne(r.Context(), `
        select series_instance_uid
        from file_series
        where file_id = $1
    `, fileID)
	if err != nil {
		return err
	}
	if !found {
		return errNoRecords
	}
	return a.roisForSeries(w, r, row.GetString("series_instance_uid"))
}

func (a *App) contoursForSOP(w http.ResponseWriter, r *http.Request, sop string) error {
	rows, err := a.DB.Fetch(r.Context(), `
        select
                roi_num,
                roi_name,
                roi_color,
                file_sop_common.file_id as image_file_id,
                fril.file_id as file_id,
                data_set_start,
                contour_file_offset,
                contour_length,
                num_points,
                data_set_start + contour_file_offset as true_offset,
                (
                    select root_path || '/' || rel_path
                    from file_location
                    natural join file_storage_root
                    where file_location.file_id = fril.file_id
                    limit 1
                ) as filename,
                (
                    select iop
                    from file_image
                    natural join image_geometry
                    where file_image.file_id = file_sop_common.file_id
                    limit 1
                ) as iop,
                (
                    select ipp
                    from file_image
                    natural join image_geometry
                    where file_image.file_id = file_sop_common.file_id
                    limit 1
                ) as ipp,
                (
                    select pixel_spacing
                    from file_image
                    natural join image
                    where file_image.file_id = file_sop_common.file_id
                    limit 1
                ) as pixel_spacing
        from file_sop_common
        join file_roi_image_linkage fril
                on fril.linked_sop_instance_uid = file_sop_common.sop_instance_uid
        join ctp_file
                on fril.file_id = ctp_file.file_id
        join file_meta
                on file_meta.file_id = fril.file_id
        natural join roi
        where sop_instance_uid = $1
    `, sop)
	if err != nil {
		return err
	}

	contours := make([]any, 0, len(rows))
	for _, row := range rows {
		points, err := transformedContour(row)
		if err != nil {
			return err
		}
		color, _ := row.Get("roi_color").(string)
		contours = append(contours, map[string]any{
			"name":   row.Get("roi_name"),
			"color":  dicom.FormatColor(color),
			"points": points,
		})
	}
	return httpx.JSON(w, contours)
}

// transformedContour ports roi.get_transformed_contour: read the raw
// contour bytes out of the RTSTRUCT file and project them into pixel
// coordinates for the linked image.
func transformedContour(row db.Row) ([][2]int64, error) {
	f, err := os.Open(row.GetString("filename"))
	if err != nil {
		return nil, err
	}
	defer f.Close()

	length := row.GetInt("contour_length")
	data := make([]byte, length)
	if _, err := f.ReadAt(data, row.GetInt("true_offset")); err != nil {
		return nil, err
	}

	points, err := dicom.ParseContourPoints(string(data))
	if err != nil {
		return nil, err
	}
	if int64(len(points)) != row.GetInt("num_points") {
		log.Printf("Warning: actual point count != calculated count!")
	}

	iop, err := dicom.ParseBackslashFloats(row.GetString("iop"))
	if err != nil {
		return nil, err
	}
	ipp, err := dicom.ParseBackslashFloats(row.GetString("ipp"))
	if err != nil {
		return nil, err
	}
	spacing, err := dicom.ParseBackslashFloats(row.GetString("pixel_spacing"))
	if err != nil {
		return nil, err
	}

	xform := dicom.MakeTransform(iop, ipp)
	return dicom.TransformContour(points, xform, spacing), nil
}

func (a *App) getContoursForSOP(w http.ResponseWriter, r *http.Request) error {
	return a.contoursForSOP(w, r, pathStr(r, "sop_instance_uid"))
}

func (a *App) getContoursForFile(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	row, found, err := a.DB.FetchOne(r.Context(), `
        select sop_instance_uid
        from file_sop_common
        where file_id = $1
    `, fileID)
	if err != nil {
		return err
	}
	if !found {
		return errNoRecords
	}
	return a.contoursForSOP(w, r, row.GetString("sop_instance_uid"))
}
