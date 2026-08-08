package routes

import (
	"net/http"

	"tcia/posda-api/internal/httpx"
)

// registerWork ports papi/routes/work.py.
func (a *App) registerWork(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/work/items", a.getWorkItems)
	a.protected(mux, "GET /v1/work/items/{work_id}", a.getWorkItem)
	a.protected(mux, "GET /v1/work/queues/{queue_name}", a.getWorkQueue)
}

func (a *App) getWorkItems(w http.ResponseWriter, r *http.Request) error {
	if !r.URL.Query().Has("status") {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"query parameter \"status\" is required")
	}
	count, err := queryInt(r, "count", 20)
	if err != nil {
		return err
	}
	return a.fetchFirstColumn(w, r, `
        select
            work_id
        from
            work
        where
            status = $1
        limit $2
    `, r.URL.Query().Get("status"), count)
}

func (a *App) getWorkItem(w http.ResponseWriter, r *http.Request) error {
	workID, err := pathInt(r, "work_id")
	if err != nil {
		return err
	}
	return a.fetchOneJSON(w, r, `
          select
                work.*,
                background_subprocess_id,
                activity_id,
                invoking_user,
                now() - when_invoked as since_invocation,
                command_line,
                when_invoked,
                user_to_notify,
                node_hostname
            from
                work
                left join subprocess_invocation using (subprocess_invocation_id)
                left join background_subprocess using (subprocess_invocation_id)
                left join activity_task_status using (subprocess_invocation_id)
            where work_id = $1
    `, workID)
}

func (a *App) getWorkQueue(w http.ResponseWriter, r *http.Request) error {
	count, err := queryInt(r, "count", 20)
	if err != nil {
		return err
	}
	return a.fetchFirstColumn(w, r, `
        select
            work_id
        from
            work
        where
            background_queue_name = $1
            and finished = false
            and running = false
            and failed = false
        order by work_id desc
        limit $2
    `, pathStr(r, "queue_name"), count)
}
