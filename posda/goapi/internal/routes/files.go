package routes

import (
	"fmt"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"

	"tcia/posda-api/internal/archive"
	"tcia/posda-api/internal/httpx"
)

// registerFiles ports papi/routes/files.py.
func (a *App) registerFiles(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "listing all files is not allowed")
	})
	a.public(mux, "GET /v1/files", notAllowed)
	a.public(mux, "GET /v1/files/{$}", notAllowed)

	a.protected(mux, "GET /v1/files/listfiles", a.getListFiles)
	a.protected(mux, "GET /v1/files/{file_id}", a.getSingleFile)
	a.protected(mux, "GET /v1/files/series/{spec}", a.getSeriesZip)
	a.protected(mux, "GET /v1/files/iec/{iec}", a.getIECZip)
	// The per-file subresources share one wildcard pattern because
	// ServeMux would otherwise consider them ambiguous against the
	// series/iec literal prefixes above.
	a.protected(mux, "GET /v1/files/{file_id}/{action...}", a.fileSubresource)
}

func (a *App) fileSubresource(w http.ResponseWriter, r *http.Request) error {
	switch pathStr(r, "action") {
	case "pixels":
		return a.getPixelData(w, r)
	case "data", "data.gz":
		return a.getFileData(w, r)
	case "path":
		return a.getFilePath(w, r)
	case "details":
		return a.getFileDetails(w, r)
	}
	return httpx.NewError(http.StatusNotFound, "Not Found")
}

func (a *App) getListFiles(w http.ResponseWriter, r *http.Request) error {
	root := queryStr(r, "path", "")
	var files []any
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil // os.walk silently skips unreadable entries
		}
		if d.IsDir() {
			return nil
		}
		files = append(files, path)
		if len(files) > 5000 {
			return httpx.NewError(http.StatusBadRequest,
				"More than 5000 results. I refuse.")
		}
		return nil
	})
	if err != nil {
		return err
	}
	if files == nil {
		files = []any{}
	}
	return httpx.JSON(w, files)
}

func (a *App) getSingleFile(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	return a.fetchOneJSON(w, r, `
        select *
        from file
        where file_id = $1
    `, fileID)
}

func (a *App) getSeriesZip(w http.ResponseWriter, r *http.Request) error {
	spec, err := parseSeriesSpec(pathStr(r, "spec"))
	if err != nil {
		return err
	}

	var (
		sql      string
		args     []any
		fileName string
	)
	switch {
	case spec.TimepointID != nil:
		sql = `
        select distinct root_path || '/' || rel_path as file
        from file_series
        natural left join ctp_file
        natural left join file_location
        natural left join file_storage_root
        natural left join activity_timepoint_file
        where series_instance_uid = $1
          and activity_timepoint_id = $2
        `
		args = []any{spec.UID, *spec.TimepointID}
		fileName = fmt.Sprintf("%s_tp%d.zip", spec.UID, *spec.TimepointID)

	case spec.ActivityID != nil:
		sql = `
        select distinct root_path || '/' || rel_path as file
        from file_series
        natural left join ctp_file
        natural left join file_location
        natural left join file_storage_root
        natural left join activity_timepoint_file
        where series_instance_uid = $1
        and activity_timepoint_id = (
            select max(activity_timepoint_id)
            from activity_timepoint
            where activity_id = $2
        )
        `
		args = []any{spec.UID, *spec.ActivityID}
		fileName = fmt.Sprintf("%s_act%d.zip", spec.UID, *spec.ActivityID)

	default:
		sql = `
        select distinct root_path || '/' || rel_path as file
        from file_series
        natural left join ctp_file
        natural left join file_location
        natural left join file_storage_root
        where series_instance_uid = $1
        `
		args = []any{spec.UID}
		fileName = fmt.Sprintf("%s_ALL.zip", spec.UID)
	}

	rows, err := a.DB.Fetch(r.Context(), sql, args...)
	if err != nil {
		return err
	}
	files := make([]string, 0, len(rows))
	for _, row := range rows {
		files = append(files, row.GetString("file"))
	}
	return archive.StreamZip(w, files, fileName)
}

func (a *App) getIECZip(w http.ResponseWriter, r *http.Request) error {
	iec, err := pathInt(r, "iec")
	if err != nil {
		return err
	}
	rows, err := a.DB.Fetch(r.Context(), `
	select root_path || '/' || rel_path as file
	from
	image_equivalence_class_input_image
    natural left join ctp_file
	natural left join file_location
	natural left join file_storage_root
	where image_equivalence_class_id = $1
    `, iec)
	if err != nil {
		return err
	}
	files := make([]string, 0, len(rows))
	for _, row := range rows {
		files = append(files, row.GetString("file"))
	}
	return archive.StreamZip(w, files, fmt.Sprintf("%d.zip", iec))
}

// pyStr renders a value the way Python's str() does inside the Q-DICOM
// response headers (None for nulls, True/False for bools).
func pyStr(v any) string {
	switch t := v.(type) {
	case nil:
		return "None"
	case bool:
		if t {
			return "True"
		}
		return "False"
	}
	return fmt.Sprint(v)
}

func (a *App) getPixelData(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}

	row, found, err := a.DB.FetchOne(r.Context(), `
        select distinct
            root_path || '/' || rel_path as file,
            pixel_data_offset as file_offset,
            pixel_data_length as size,
            bits_stored,
            bits_allocated,
            pixel_representation,
            pixel_columns,
            pixel_rows,
            photometric_interpretation,

            slope,
            intercept,

            window_width,
            window_center,
            pixel_pad,
            samples_per_pixel,
            planar_configuration,
            coalesce(number_of_frames, 1) as number_of_frames

        from
            file_image
            natural join image
            natural join dicom_file
            natural join file_location
            natural join file_storage_root
            natural join file_equipment

            natural left join file_slope_intercept
            natural left join slope_intercept

            natural left join file_win_lev
            natural left join window_level

        where file_image.file_id = $1
    `, fileID)
	if err != nil {
		return err
	}
	if !found {
		return errNoRecords
	}

	data, err := readFileFrom(row.GetString("file"), row.GetInt("file_offset"))
	if err != nil {
		return err
	}

	headers := map[string]string{
		"Q-DICOM-Rows":              pyStr(row.Get("pixel_rows")),
		"Q-DICOM-Cols":              pyStr(row.Get("pixel_columns")),
		"Q-DICOM-Size":              pyStr(row.Get("size")),
		"Q-DICOM-Bits-Stored":       pyStr(row.Get("bits_stored")),
		"Q-DICOM-Bits-Allocated":    pyStr(row.Get("bits_allocated")),
		"Q-DICOM-PixelRep":          pyStr(row.Get("pixel_representation")),
		"Q-DICOM-Slope":             pyStr(row.Get("slope")),
		"Q-DICOM-Intercept":         pyStr(row.Get("intercept")),
		"Q-DICOM-Window-Center":     pyStr(row.Get("window_center")),
		"Q-DICOM-Window-Width":      pyStr(row.Get("window_width")),
		"Q-DICOM-Pixel-Pad":         pyStr(row.Get("pixel_pad")),
		"Q-DICOM-Samples-Per-Pixel": pyStr(row.Get("samples_per_pixel")),
		"Q-DICOM-PhotoRep":          pyStr(row.Get("photometric_interpretation")),
		"Q-DICOM-Planar-Config":     pyStr(row.Get("planar_configuration")),
		"Q-DICOM-Num-of-Frames":     pyStr(row.Get("number_of_frames")),
	}
	for k, v := range headers {
		w.Header().Set(k, v)
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	_, err = w.Write(data)
	return err
}

// fileOnDisk resolves a file_id to its path via file_location.
func (a *App) fileOnDisk(r *http.Request, fileID int64) (string, error) {
	row, found, err := a.DB.FetchOne(r.Context(), `
        select
            root_path || '/' || rel_path as file,
            size
        from file
        natural join file_location
        natural join file_storage_root
        where file_id = $1
    `, fileID)
	if err != nil {
		return "", err
	}
	if !found {
		return "", errNoRecords
	}
	path := row.GetString("file")
	if _, err := os.Stat(path); err != nil {
		return "", httpx.NewError(http.StatusNotFound, "File not found on disk")
	}
	return path, nil
}

func (a *App) getFileData(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	path, err := a.fileOnDisk(r, fileID)
	if err != nil {
		return err
	}
	return serveFile(w, r, path, "", nil)
}

func (a *App) getFilePath(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	return a.fetchOneJSON(w, r, `
        select
            root_path || '/' || rel_path as file_path
        from file
        natural join file_location
        natural join file_storage_root
        where file_id = $1
    `, fileID)
}

func (a *App) getFileDetails(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	return a.fetchOneJSON(w, r, `
        select distinct
            root_path || '/' || rel_path as file,
            file_offset,
            size,
            bits_stored,
            bits_allocated,
            pixel_representation,
            pixel_columns,
            pixel_rows,
            photometric_interpretation,

            slope,
            intercept,

            window_width,
            window_center,
            pixel_pad,

            project_name,
            site_name,
            sop_instance_uid,
            series_instance_uid,
            modality,
            body_part_examined,
            series_description,
            patient_id,
            study_instance_uid

        from
            file
            natural left join file_image
            natural left join image
            natural left join unique_pixel_data
            natural left join pixel_location
            natural left join file_location
            natural left join file_storage_root
            natural left join file_equipment
            natural left join file_sop_common
            natural left join file_series
            natural left join ctp_file
            natural left join file_patient
            natural left join file_study

            natural left join file_slope_intercept
            natural left join slope_intercept

            natural left join file_win_lev
            natural left join window_level

        where file.file_id = $1
    `, fileID)
}
