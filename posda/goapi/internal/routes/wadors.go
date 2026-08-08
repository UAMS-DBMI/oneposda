package routes

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/httpx"
)

// registerWadoRS ports papi/routes/wadors.py: the minimal WADO-RS
// subset used by the Cornerstone viewer.
func (a *App) registerWadoRS(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/wadors/studies/{study}/series/{series}/instances/{sop}/frames/{frame}", a.wadorsFrames)
	a.protected(mux, "GET /v1/wadors/studies/{study}/series/{series}/metadata", a.wadorsMetadata)
}

// parseWadorsStudy splits the "iec:123" / "timepoint:5" / "activity:7"
// study selector used in place of a StudyInstanceUID.
func parseWadorsStudy(study string) (kind string, id int64, err error) {
	kind, raw, found := strings.Cut(study, ":")
	if !found {
		return "", 0, httpx.NewError(http.StatusNotFound, "Not Found")
	}
	id, perr := strconv.ParseInt(raw, 10, 64)
	if perr != nil {
		return "", 0, httpx.NewError(http.StatusUnprocessableEntity,
			"study selector id must be an integer")
	}
	switch kind {
	case "iec", "timepoint", "activity":
		return kind, id, nil
	}
	return "", 0, httpx.NewError(http.StatusNotFound, "Not Found")
}

func (a *App) wadorsFrames(w http.ResponseWriter, r *http.Request) error {
	kind, id, err := parseWadorsStudy(pathStr(r, "study"))
	if err != nil {
		return err
	}
	sop := pathStr(r, "sop")

	var row db.Row
	var found bool
	switch kind {
	case "iec":
		row, found, err = a.DB.FetchOne(r.Context(), `
        select
            root_path || '/' || rel_path as file,
            pixel_data_offset as file_offset,
            xfer_syntax
        from
                image_equivalence_class_input_image
                natural join dicom_file
                natural join file_meta
                natural join file_sop_common
                natural join file_location
                natural join file_storage_root
        where
                image_equivalence_class_id = $1
                and sop_instance_uid = $2
    `, id, sop)

	case "timepoint":
		row, found, err = a.DB.FetchOne(r.Context(), `
        select
            root_path || '/' || rel_path as file,
            pixel_data_offset as file_offset,
            xfer_syntax
        from
                activity_timepoint_file
                natural join dicom_file
                natural join file_meta
                natural join file_sop_common
                natural join file_location
                natural join file_storage_root
        where
                activity_timepoint_id = $1
                and sop_instance_uid = $2
    `, id, sop)

	case "activity":
		// The Python handler shares code with the timepoint variant and
		// queries with timepoint_id=None, which matches nothing.
		found = false
	}
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
	w.Header().Set("Content-Type",
		fmt.Sprintf("application/octet-stream; transfer-syntax=%s",
			row.GetString("xfer_syntax")))
	_, err = w.Write(data)
	return err
}

func (a *App) wadorsMetadata(w http.ResponseWriter, r *http.Request) error {
	kind, id, err := parseWadorsStudy(pathStr(r, "study"))
	if err != nil {
		return err
	}
	series := pathStr(r, "series")

	var rows []db.Row
	switch kind {
	case "activity":
		// Python raises HTTPException("not implemented yet") which
		// crashes response rendering -> 500.
		return httpx.NewError(http.StatusInternalServerError, "Internal Server Error")

	case "timepoint":
		rows, err = a.DB.Fetch(r.Context(), `
        select distinct
            root_path || '/' || rel_path as file,
            pixel_data_offset as file_offset,
            pixel_data_length as size,
            bits_stored,
            bits_allocated,
            high_bit,
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
            coalesce(number_of_frames, 1) as number_of_frames,
            iop,
            ipp,
            study_instance_uid,
            series_instance_uid,
            sop_instance_uid,
            pixel_spacing,
            file_id

        from
            activity_timepoint_file
            natural join file_series
            natural join file_study
            natural join file_sop_common
            natural join file_image
            natural join image
            natural join image_geometry
            natural join dicom_file
            natural join file_location
            natural join file_storage_root
            natural join file_equipment

            natural left join file_slope_intercept
            natural left join slope_intercept

            natural left join file_win_lev
            natural left join window_level

        where
            activity_timepoint_id = $1
            and series_instance_uid = $2
        order by file_id desc
    `, id, series)

	case "iec":
		rows, err = a.DB.Fetch(r.Context(), `
        select distinct
            root_path || '/' || rel_path as file,
            pixel_data_offset as file_offset,
            pixel_data_length as size,
            bits_stored,
            bits_allocated,
            high_bit,
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
            coalesce(number_of_frames, 1) as number_of_frames,
            iop,
            ipp,
            study_instance_uid,
            series_instance_uid,
            sop_instance_uid,
            pixel_spacing,
            file_id,
            modality

        from
			image_equivalence_class_input_image
            natural join file_series
            natural join file_study
            natural join file_sop_common
            natural join file_image
            natural join image
            natural join dicom_file
            natural join file_location
            natural join file_storage_root
            natural join file_equipment

            natural left join image_geometry

            natural left join file_slope_intercept
            natural left join slope_intercept

            natural left join file_win_lev
            natural left join window_level

        where
			image_equivalence_class_id = $1
        order by file_id desc
    `, id)
	}
	if err != nil {
		return err
	}

	out := make([]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, wadorsConvert(row))
	}
	return httpx.JSON(w, out)
}

// wadorsValue mirrors ValueModel.from_record.
type wadorsValue struct {
	Value []any  `json:"Value"`
	VR    string `json:"vr"`
}

func newWadorsValue(vr string, v any) wadorsValue {
	var values []any
	switch t := v.(type) {
	case nil:
		values = []any{}
	case string:
		if strings.Contains(t, `\`) {
			for _, part := range strings.Split(t, `\`) {
				values = append(values, part)
			}
		} else {
			values = []any{t}
		}
	default:
		values = []any{v}
	}

	switch vr {
	case "US":
		conv := make([]any, len(values))
		for i, v := range values {
			conv[i] = toInt(v)
		}
		values = conv
	case "DS":
		conv := make([]any, len(values))
		for i, v := range values {
			conv[i] = toFloat(v)
		}
		values = conv
	}
	return wadorsValue{Value: values, VR: vr}
}

func toInt(v any) any {
	switch t := v.(type) {
	case string:
		if n, err := strconv.ParseInt(strings.TrimSpace(t), 10, 64); err == nil {
			return n
		}
		return v
	}
	return v
}

func toFloat(v any) any {
	switch t := v.(type) {
	case string:
		if f, err := strconv.ParseFloat(strings.TrimSpace(t), 64); err == nil {
			return f
		}
		return v
	case int64:
		return float64(t)
	case int32:
		return float64(t)
	}
	return v
}

func wadorsConvert(row db.Row) map[string]wadorsValue {
	c := newWadorsValue
	ret := map[string]wadorsValue{
		"00280030": c("DS", row.Get("pixel_spacing")),
		"00080018": c("UI", row.Get("sop_instance_uid")),
		"0020000E": c("UI", row.Get("series_instance_uid")),
		"0020000D": c("UI", row.Get("study_instance_uid")),
		"00280010": c("US", row.Get("pixel_rows")),
		"00280011": c("US", row.Get("pixel_columns")),
		"00280101": c("US", row.Get("bits_stored")),
		"00280100": c("US", row.Get("bits_allocated")),
		"00280102": c("US", row.Get("high_bit")),
		"00280103": c("US", row.Get("pixel_representation")),
		"00281053": c("DS", row.Get("slope")),
		"00281052": c("DS", row.Get("intercept")),
		"00281050": c("DS", row.Get("window_center")),
		"00281051": c("DS", row.Get("window_width")),
		"00280002": c("US", row.Get("samples_per_pixel")),
		"00280004": c("CS", row.Get("photometric_interpretation")),
		"00080060": c("CS", row.Get("modality")),
	}
	if v := row.Get("iop"); v != nil {
		ret["00200037"] = c("DS", v)
	}
	if v := row.Get("ipp"); v != nil {
		ret["00200032"] = c("DS", v)
	}
	return ret
}
