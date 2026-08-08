package routes

import (
	"fmt"
	"math"
	"net/http"
	"strconv"
	"strings"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/httpx"
)

// registerActivities ports papi/routes/activities.py.
func (a *App) registerActivities(mux *http.ServeMux) {
	list := a.Auth.Middleware(a.getAllActivities)
	a.public(mux, "GET /v1/activities", list)
	a.public(mux, "GET /v1/activities/{$}", list)

	a.protected(mux, "GET /v1/activities/{activity_id}", a.getActivity)
	a.protected(mux, "GET /v1/activities/{activity_id}/{timeline_id}", a.getTimelineEntry)
	a.protected(mux, "GET /v1/activities/{activity_id}/{timeline_id}/input",
		a.timelineEntryFile("input_file_id"))
	a.protected(mux, "GET /v1/activities/{activity_id}/{timeline_id}/output",
		a.timelineEntryFile("stdout_file_id"))
	a.protected(mux, "GET /v1/activities/{activity_id}/{timeline_id}/errors",
		a.timelineEntryFile("stderr_file_id"))
}

// filterRowTo mimics a FastAPI response_model: only the named columns
// survive, in model order.
func filterRowTo(row db.Row, cols ...string) db.Row {
	out := db.NewRow()
	for _, c := range cols {
		out.Set(c, row.Get(c))
	}
	return out
}

// pydanticDatetime rewrites a UTC "+00:00" timestamp string into the
// "Z" form pydantic v2 uses when serializing datetime model fields.
func pydanticDatetime(v any) any {
	if s, ok := v.(string); ok && strings.HasSuffix(s, "+00:00") {
		return strings.TrimSuffix(s, "+00:00") + "Z"
	}
	return v
}

// pydanticDuration converts an interval (already reduced to total
// seconds by the db layer) into pydantic v2's ISO 8601 form, e.g.
// "PT32.486489S", "P1DT2H", "PT0S".
func pydanticDuration(v any) any {
	f, ok := v.(db.PyFloat)
	if !ok {
		return v
	}
	us := int64(math.Round(float64(f) * 1e6))
	sign := ""
	if us < 0 {
		sign = "-"
		us = -us
	}

	days := us / 86_400_000_000
	us -= days * 86_400_000_000
	hours := us / 3_600_000_000
	us -= hours * 3_600_000_000
	minutes := us / 60_000_000
	us -= minutes * 60_000_000
	seconds := float64(us) / 1e6

	out := sign + "P"
	if days > 0 {
		out += strconv.FormatInt(days, 10) + "D"
	}
	timePart := ""
	if hours > 0 {
		timePart += strconv.FormatInt(hours, 10) + "H"
	}
	if minutes > 0 {
		timePart += strconv.FormatInt(minutes, 10) + "M"
	}
	if seconds != 0 || (days == 0 && timePart == "") {
		timePart += strconv.FormatFloat(seconds, 'f', -1, 64) + "S"
	}
	if timePart != "" {
		out += "T" + timePart
	}
	return out
}

func (a *App) getAllActivities(w http.ResponseWriter, r *http.Request) error {
	rows, err := a.DB.Fetch(r.Context(), `
        select *
        from activity
        where when_closed is null
    `)
	if err != nil {
		return err
	}

	out := make([]any, 0, len(rows))
	for _, row := range rows {
		entry := filterRowTo(row,
			"activity_id", "brief_description", "who_created", "when_created")
		entry.Set("when_created", pydanticDatetime(entry.Get("when_created")))
		out = append(out, entry)
	}
	return httpx.JSON(w, out)
}

func (a *App) getActivity(w http.ResponseWriter, r *http.Request) error {
	activityID, err := pathInt(r, "activity_id")
	if err != nil {
		return err
	}
	rows, err := a.DB.Fetch(r.Context(), `

        with timepoints as (
            select
                activity_id,
                a.when_created as activity_created,
                brief_description as activity_description,
                activity_timepoint_id,
                t.when_created as timepoint_created,
                comment,
                creating_user,
                (
                    select count(file_id)
                    from activity_timepoint_file atf
                    where atf.activity_timepoint_id = t.activity_timepoint_id
                ) as file_count
            from
                activity a
                join activity_timepoint t using (activity_id)
            where
                activity_id = $1
            order by
                t.when_created desc

        ), inbox_content as (
        select
            user_name,
            user_inbox_content_id as timeline_id,
            operation_name,
            when_script_started as when,
            when_script_ended as ended,
            when_script_ended - when_script_started as duration,
            file_id,
            subprocess_invocation_id as sub_id,
            command_line,
            file_id_in_posda as spreadsheet_file_id

            from activity_inbox_content
            natural join user_inbox
            natural join user_inbox_content
            natural join background_subprocess_report
            natural join background_subprocess
            natural join subprocess_invocation
            natural left join spreadsheet_uploaded
        where
            activity_id = $1
        order by
            when_script_started desc
        )

        select *
        from inbox_content
        left join timepoints
            on timepoints.timepoint_created
                between inbox_content.when and inbox_content.ended
    `, activityID)
	if err != nil {
		return err
	}

	out := make([]any, 0, len(rows))
	for _, row := range rows {
		entry := filterRowTo(row,
			"timeline_id", "operation_name", "duration", "activity_timepoint_id",
			"file_count", "user_name", "command_line", "when")
		entry.Set("duration", pydanticDuration(entry.Get("duration")))
		entry.Set("when", pydanticDatetime(entry.Get("when")))
		out = append(out, entry)
	}
	return httpx.JSON(w, out)
}

func (a *App) getTimelineEntry(w http.ResponseWriter, r *http.Request) error {
	timelineID, err := pathInt(r, "timeline_id")
	if err != nil {
		return err
	}

	reportRows, err := a.DB.Fetch(r.Context(), `
        select
            file_id, name
        from
                background_subprocess_report
        where background_subprocess_id = (
                select background_subprocess_id
                from background_subprocess
                where subprocess_invocation_id = $1
        )
    `, timelineID)
	if err != nil {
		return err
	}

	row, found, err := a.DB.FetchOne(r.Context(), `
        select
            *
        from
            subprocess_invocation
            natural join background_subprocess
            join activity_task_status using (subprocess_invocation_id)
            left join activity_timepoint
                on activity_timepoint.activity_id = activity_task_status.activity_id
                and activity_timepoint.when_created
                    between background_subprocess.when_script_started
                    and background_subprocess.when_script_ended
        where
            background_subprocess.subprocess_invocation_id = $1
    `, timelineID)
	if err != nil {
		return err
	}
	if !found {
		// Python fails constructing the response model -> 500.
		return httpx.ErrInternal
	}

	out := filterRowTo(row,
		"command_line", "start_time", "end_time", "operation_name",
		"invoking_user", "activity_timepoint_id")
	out.Set("reports", reportRows)
	return httpx.JSON(w, out)
}

// timelineEntryFile serves the input/stdout/stderr file recorded in
// the work table for a subprocess.
func (a *App) timelineEntryFile(column string) httpx.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		timelineID, err := pathInt(r, "timeline_id")
		if err != nil {
			return err
		}
		row, found, err := a.DB.FetchOne(r.Context(), fmt.Sprintf(`
        select %s
        from work
        where subprocess_invocation_id = $1
    `, column), timelineID)
		if err != nil {
			return err
		}
		if !found {
			return errNoRecords
		}
		fileID := row.GetInt(column)
		path, err := a.fileOnDisk(r, fileID)
		if err != nil {
			return err
		}
		return serveFile(w, r, path, "", map[string]string{
			"P-file_id": fmt.Sprint(fileID),
		})
	}
}
