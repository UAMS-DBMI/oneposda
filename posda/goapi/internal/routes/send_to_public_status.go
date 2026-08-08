package routes

import (
	"html/template"
	"net/http"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/evilparse"
	"tcia/posda-api/internal/httpx"
)

// registerSendToPublicStatus ports papi/routes/send_to_public_status.py.
func (a *App) registerSendToPublicStatus(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "test error, not allowed")
	})
	a.public(mux, "GET /v1/send_to_public_status", notAllowed)
	a.public(mux, "GET /v1/send_to_public_status/{$}", notAllowed)

	a.protected(mux, "GET /v1/send_to_public_status/report/{subprocess_invocation_id}", a.publicCopyReport)

	a.protected(mux, "GET /v1/send_to_public_status/find_send_ready_to_begin_status_updates",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select distinct
                subprocess_invocation_id
        from
                activity_task_status
                natural join public_copy_status
        where
                manual_update = true
    `)
		})

	a.protected(mux, "GET /v1/send_to_public_status/get_success_percentage_for_send/{subprocess_invocation_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "subprocess_invocation_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        select
            ('' || success::text || ' ' || ((count(*)/(select  sum(c) as t from
            ( select
                count(file_id) as c
                from
                    activity_timepoint_file
                where
                    activity_timepoint_id = (
                	select max(activity_timepoint_id)
                	from activity_timepoint
                	where activity_id = (
                		select activity_id
                		from activity_task_status
                		where subprocess_invocation_id = $1 )))
                		as sum_table)::float) * 100.0)::int || '%')::text as summary
        from
            public_copy_status
        where
            subprocess_invocation_id = $1
        group by
            success
            `, id)
		})

	a.protected(mux, "GET /v1/send_to_public_status/update_activity_status/{subprocess_invocation_id}/{new_status}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "subprocess_invocation_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        update
            activity_task_status
        set
            status_text = $2
        where
            activity_task_status.manual_update = true
            and subprocess_invocation_id = $1
    `, id, pathStr(r, "new_status"))
		})

	a.protected(mux, "GET /v1/send_to_public_status/finish_activity_status/{subprocess_invocation_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "subprocess_invocation_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        update
            activity_task_status
        set
            manual_update = false
        where
            activity_task_status.manual_update = true
            and subprocess_invocation_id = $1
    `, id)
		})
}

func (a *App) publicCopyReport(w http.ResponseWriter, r *http.Request) error {
	id, err := pathInt(r, "subprocess_invocation_id")
	if err != nil {
		return err
	}

	rows, err := a.DB.Fetch(r.Context(), `
        select
            success, count(file_id)
        from public_copy_status
        where subprocess_invocation_id = $1
        group by success
    `, id)
	if err != nil {
		return err
	}

	var totalFiles int64
	for _, row := range rows {
		totalFiles += row.GetInt("count")
	}

	errRows, err := a.DB.Fetch(r.Context(), `
        select
            error_message
        from public_copy_status
        where subprocess_invocation_id = $1
          and success = false
          limit 5
    `, id)
	if err != nil {
		return err
	}

	files := make([]db.Row, 0, len(errRows))
	for _, errRow := range errRows {
		file, firstError, err := evilparse.Parse(errRow.GetString("error_message"))
		if err != nil {
			// The Python eval() would blow up the whole request here.
			return err
		}
		row := db.NewRow()
		row.Set("subprocess_invocation_id", file.SubprocessInvocationID)
		row.Set("file_id", file.FileID)
		row.Set("collection", file.Collection)
		row.Set("site", file.Site)
		row.Set("site_id", file.SiteID)
		row.Set("batch", file.Batch)
		row.Set("filename", file.Filename)
		row.Set("third_party_analysis_url", file.ThirdPartyAnalysisURL)
		row.Set("error_message", evilparse.Truncate(firstError, 500))
		row.Set("curl", file.CurlCommand())
		files = append(files, row)
	}

	if queryBool(r, "pretty", false) {
		return renderPrettyReport(w, id, rows, totalFiles, files)
	}

	return httpx.JSON(w, map[string]any{
		"overal_status":  rows,
		"total_files":    totalFiles,
		"first_5_errors": files,
	})
}

var prettyReportTemplate = template.Must(template.New("report").Parse(`
<html>
<head>
    <title>Report for {{.InvocID}}</title>
    <style type="text/css">
        body {
            background-color: #EEEEEE;
        }
        td, th {
            border: 2px solid #C7C7C7;
            padding: 10px;
        }
        th {
            text-align: right;
        }
        table {
            margin-bottom: 1em;
            border-collapse: collapse;
        }
    </style>
</head>
<body>
<h1>Public Copy Report for ID#{{.InvocID}}</h1>

<h3>Overall status</h3>
<table>
<tr>
    <th>Count of files</th>
    <th>Sucessful?</th>
</tr>
{{range .Rows}}
<tr>
    <td>{{.Count}}</td>
    <td>{{.Success}}</td>
</tr>
{{end}}
<tr>
    <td>{{.TotalFiles}}</td>
    <td>Both</td>
</tr>
</table>

<h3>First 5 files that failed</h3>
{{range .Files}}
<table>
<tr>
    <th>file_id</th>
    <td><a href="/viewer/file/{{.FileID}}" target="_blank">{{.FileID}}</a></td>
</tr>
<tr>
    <th>collection</th>
    <td>{{.Collection}}</td>
</tr>
<tr>
    <th>site</th>
    <td>{{.Site}}</td>
</tr>
<tr>
    <th>site_id</th>
    <td>{{.SiteID}}</td>
</tr>
<tr>
    <th>filename</th>
    <td>{{.Filename}}</td>
</tr>
<tr>
    <th>batch</th>
    <td>{{.Batch}}</td>
</tr>
<tr>
    <th>third_party_analysis_url</th>
    <td>{{.ThirdPartyAnalysisURL}}</td>
</tr>
<tr>
    <th>error_message</th>
    <td>{{.ErrorMessage}}</td>
</tr>
<tr>
    <th>API Command for NBIA Debugging</th>
    <td>
        {{.Curl}}
    </td>
</tr>
</table>
{{end}}

</body>
</html>
    `))

func renderPrettyReport(w http.ResponseWriter, invocID int64,
	rows []db.Row, totalFiles int64, files []db.Row) error {

	type statusRow struct {
		Count   any
		Success any
	}
	type fileRow struct {
		FileID, Collection, Site, SiteID, Filename, Batch any
		ThirdPartyAnalysisURL, ErrorMessage, Curl         any
	}

	data := struct {
		InvocID    int64
		Rows       []statusRow
		TotalFiles int64
		Files      []fileRow
	}{InvocID: invocID, TotalFiles: totalFiles}

	for _, row := range rows {
		data.Rows = append(data.Rows, statusRow{
			Count:   row.Get("count"),
			Success: row.Get("success"),
		})
	}
	for _, f := range files {
		data.Files = append(data.Files, fileRow{
			FileID:                f.Get("file_id"),
			Collection:            f.Get("collection"),
			Site:                  f.Get("site"),
			SiteID:                f.Get("site_id"),
			Filename:              f.Get("filename"),
			Batch:                 f.Get("batch"),
			ThirdPartyAnalysisURL: f.Get("third_party_analysis_url"),
			ErrorMessage:          f.Get("error_message"),
			Curl:                  f.Get("curl"),
		})
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	return prettyReportTemplate.Execute(w, data)
}
