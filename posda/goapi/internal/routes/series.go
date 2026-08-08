package routes

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/httpx"
)

// seriesSpec is a parsed "{series_instance_uid}", with optional
// "@{activity_id}" or ":{activity_timepoint_id}" suffix — FastAPI
// expressed these as three separate routes; here the suffix is parsed
// out of the path segment.
type seriesSpec struct {
	UID         string
	ActivityID  *int64
	TimepointID *int64
}

func parseSeriesSpec(spec string) (seriesSpec, error) {
	// '@' is checked first, matching the Python route registration order.
	if i := strings.LastIndex(spec, "@"); i >= 0 {
		id, err := strconv.ParseInt(spec[i+1:], 10, 64)
		if err != nil {
			return seriesSpec{}, httpx.NewError(http.StatusUnprocessableEntity,
				"activity_id must be an integer")
		}
		return seriesSpec{UID: spec[:i], ActivityID: &id}, nil
	}
	if i := strings.LastIndex(spec, ":"); i >= 0 {
		id, err := strconv.ParseInt(spec[i+1:], 10, 64)
		if err != nil {
			return seriesSpec{}, httpx.NewError(http.StatusUnprocessableEntity,
				"activity_timepoint_id must be an integer")
		}
		return seriesSpec{UID: spec[:i], TimepointID: &id}, nil
	}
	return seriesSpec{UID: spec}, nil
}

// registerSeries ports papi/routes/series.py.
func (a *App) registerSeries(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "listing all series is not allowed")
	})
	a.public(mux, "GET /v1/series", notAllowed)
	a.public(mux, "GET /v1/series/{$}", notAllowed)

	a.protected(mux, "GET /v1/series/{spec}", a.getSingleSeries)
	a.protected(mux, "GET /v1/series/{spec}/ohif", a.getOhifConfig)
	a.protected(mux, "GET /v1/series/{spec}/frames", a.getSeriesFrames)
	a.protected(mux, "GET /v1/series/{spec}/files", a.getSeriesFileIDs)
	a.protected(mux, "GET /v1/series/{spec}/activities", a.getSeriesActivities)
}

func (a *App) getSingleSeries(w http.ResponseWriter, r *http.Request) error {
	// The detail route never parses @/: suffixes (neither does FastAPI).
	return a.fetchOneJSON(w, r, `
        select distinct
            series_instance_uid,
            series_date,
            series_time::text,
            modality,
            laterality,
            series_description,
            count(file_id) as file_count
        from file_series
        where series_instance_uid = $1
        group by
            series_instance_uid,
            series_date,
            series_time,
            modality,
            laterality,
            series_description
    `, pathStr(r, "spec"))
}

func (a *App) getOhifConfig(w http.ResponseWriter, r *http.Request) error {
	uid := pathStr(r, "spec")
	rows, err := a.DB.Fetch(r.Context(), `
        select
            study_instance_uid,
            series_instance_uid,
            series_description,
            sop_instance_uid,
            file_id,
            pixel_columns,
            pixel_rows,
            bits_allocated,
            instance_number,
            image_type,
            samples_per_pixel,
            photometric_interpretation,
            bits_stored,
            high_bit,
            pixel_representation,
            pixel_spacing,
            iop,
            ipp,
            modality

        from file_series
        natural join file_study
        natural join file_sop_common
        natural join file_image
        natural join image
        natural join file_image_geometry
        natural join image_geometry
        where series_instance_uid = $1

        order by
            case instance_number
                when '' then '0'
                when null then '0'
                else instance_number
            end::int
    `, uid)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		// Python indexes results[0] unconditionally and 500s on empty.
		return httpx.NewError(http.StatusInternalServerError, "Internal Server Error")
	}

	dcmList := func(v any) any {
		s, ok := v.(string)
		if !ok {
			return []any{}
		}
		return strings.Split(s, `\`)
	}

	instances := make([]any, 0, len(rows))
	for _, row := range rows {
		metadata := map[string]any{
			"Columns":                   row.Get("pixel_columns"),
			"Rows":                      row.Get("pixel_rows"),
			"InstanceNumber":            row.Get("instance_number"),
			"PhotometricInterpretation": row.Get("photometric_interpretation"),
			"BitsAllocated":             row.Get("bits_allocated"),
			"BitsStored":                row.Get("bits_stored"),
			"PixelRepresentation":       row.Get("pixel_representation"),
			"SamplesPerPixel":           row.Get("samples_per_pixel"),
			"PixelSpacing":              dcmList(row.Get("pixel_spacing")),
			"HighBit":                   row.Get("high_bit"),
			"ImageOrientationPatient":   dcmList(row.Get("iop")),
			"ImagePositionPatient":      dcmList(row.Get("ipp")),
			"ImageType":                 dcmList(row.Get("image_type")),
			"Modality":                  row.Get("modality"),
			"SOPInstanceUID":            row.Get("sop_instance_uid"),
			"SeriesInstanceUID":         uid,
			"StudyInstanceUID":          row.Get("study_instance_uid"),
		}
		instances = append(instances, map[string]any{
			"metadata": metadata,
			"url":      fmt.Sprintf("dicomweb:%s/v1/files/%d/data", a.Cfg.APIURL, row.GetInt("file_id")),
		})
	}

	return httpx.JSON(w, map[string]any{
		"studies": []any{map[string]any{
			"StudyInstanceUID": rows[0].Get("study_instance_uid"),
			"series": []any{map[string]any{
				"SeriesInstanceUID": uid,
				"SeriesDescription": rows[0].Get("series_description"),
				"instances":         instances,
			}},
		}},
	})
}

const framesByTimepointQuery = `
    with timepoint_files as (
        select file_id
        from activity_timepoint_file
        where activity_timepoint_id = $2
    )
    select
        file_id,
        coalesce(number_of_frames, 1) as frames

    from
        timepoint_files
        natural join file_series
        natural join file_sop_common
        natural left join file_image
        natural left join image
    where series_instance_uid = $1
    order by
        -- sometimes instance_number is empty string or null
        case instance_number
            when '' then '0'
            when null then '0'
            else instance_number
        end::int
`

func (a *App) getSeriesFrames(w http.ResponseWriter, r *http.Request) error {
	spec, err := parseSeriesSpec(pathStr(r, "spec"))
	if err != nil {
		return err
	}

	switch {
	case spec.ActivityID != nil:
		row, _, err := a.DB.FetchOne(r.Context(), `
            select max(activity_timepoint_id)
            from activity_timepoint
            where activity_id = $1
        `, *spec.ActivityID)
		if err != nil {
			return err
		}
		return a.fetchJSON(w, r, framesByTimepointQuery, spec.UID, row.Get("max"))

	case spec.TimepointID != nil:
		return a.fetchJSON(w, r, framesByTimepointQuery, spec.UID, *spec.TimepointID)

	default:
		return a.fetchJSON(w, r, `
            select
                file_id,
                coalesce(number_of_frames, 1) as frames

            from
                file_series
                natural join file_sop_common
                natural left join file_image
                natural left join image
            where series_instance_uid = $1
            order by
                -- sometimes instance_number is empty string or null
                case instance_number
                    when '' then '0'
                    when null then '0'
                    else instance_number
                end::int
        `, spec.UID)
	}
}

func (a *App) getSeriesFileIDs(w http.ResponseWriter, r *http.Request) error {
	spec, err := parseSeriesSpec(pathStr(r, "spec"))
	if err != nil {
		return err
	}

	var rows []db.Row
	switch {
	case spec.TimepointID != nil:
		rows, err = a.DB.Fetch(r.Context(), `
            with timepoint_files as (
                select file_id
                from activity_timepoint_file
                where activity_timepoint_id = $2
            )
            select file_id
            from
                timepoint_files
                natural join file_series
                natural join file_sop_common
            where series_instance_uid = $1
            order by
                case instance_number
                    when '' then '0'
                    when null then '0'
                    else instance_number
                end::int
        `, spec.UID, *spec.TimepointID)

	case spec.ActivityID != nil:
		rows, err = a.DB.Fetch(r.Context(), `
            with timepoint_files as (
                select file_id
                from activity_timepoint_file
                where
                    activity_timepoint_id = (
                        select max(activity_timepoint_id)
                        from activity_timepoint
                        where activity_id = $2
                    )
            )
            select file_id
            from
                timepoint_files
                natural join file_series
                natural join file_sop_common
            where series_instance_uid = $1
            order by
                case instance_number
                    when '' then '0'
                    when null then '0'
                    else instance_number
                end::int
        `, spec.UID, *spec.ActivityID)

	default:
		rows, err = a.DB.Fetch(r.Context(), `
            select file_id
            from
                file_series
                natural left join file_sop_common
                natural left join ctp_file
            where series_instance_uid = $1
            order by
                case instance_number
                    when '' then '0'
                    when null then '0'
                    else instance_number
                end::int
        `, spec.UID)
	}
	if err != nil {
		return err
	}

	return httpx.JSON(w, map[string]any{"file_ids": firstColumn(rows)})
}

func (a *App) getSeriesActivities(w http.ResponseWriter, r *http.Request) error {
	uid := pathStr(r, "spec")

	activities, err := a.DB.Fetch(r.Context(), `
        select distinct
                activity_id
        from
            file_series
                natural join activity_timepoint_file
                natural join activity_timepoint
        where
            series_instance_uid = $1
    `, uid)
	if err != nil {
		return err
	}

	timepoints, err := a.DB.Fetch(r.Context(), `
        select distinct
                activity_id,
                activity_timepoint_id,
                when_created,
                creating_user
        from
            file_series
                natural join activity_timepoint_file
                natural join activity_timepoint
        where
            series_instance_uid = $1
    `, uid)
	if err != nil {
		return err
	}

	return httpx.JSON(w, map[string]any{
		"activities": firstColumn(activities),
		"timepoints": timepoints,
	})
}
