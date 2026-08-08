package routes

import (
	"net/http"

	"tcia/posda-api/internal/httpx"
)

// registerWorker ports papi/routes/worker.py.
func (a *App) registerWorker(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/worker/status/{work_id}", a.getWorkStatus)
	a.protected(mux, "POST /v1/worker/status/{work_id}/running", a.setWorkRunning)
	a.protected(mux, "POST /v1/worker/status/{work_id}/finished", a.setWorkFinished)
	a.protected(mux, "POST /v1/worker/status/{work_id}/errored", a.setWorkErrored)
	a.protected(mux, "GET /v1/worker/subprocess/{subprocess_invocation_id}", a.getSubprocessInfo)
}

func (a *App) getWorkStatus(w http.ResponseWriter, r *http.Request) error {
	workID, err := pathInt(r, "work_id")
	if err != nil {
		return err
	}
	return a.fetchOneJSON(w, r, `
        select
            work_id,
            node_hostname,
            subprocess_invocation_id,
            input_file_id,
            status,
            running,
            finished,
            failed,
            stderr_file_id,
            stdout_file_id
        from
            work
        where
            work_id = $1
    `, workID)
}

func (a *App) setWorkRunning(w http.ResponseWriter, r *http.Request) error {
	workID, err := pathInt(r, "work_id")
	if err != nil {
		return err
	}
	var details struct {
		NodeHostname *string `json:"node_hostname"`
	}
	if err := decodeJSONBody(r, &details); err != nil {
		return err
	}
	// The Python version fetches an UPDATE without RETURNING, which
	// yields an empty list response.
	return a.fetchOneJSON(w, r, `
        update
            work
        set
            running = true,
            status = 'running',
            node_hostname = $1
        where
            work_id = $2
    `, details.NodeHostname, workID)
}

// setWorkDone handles the shared finished/errored update: the two
// tracked file ids are pulled out of the JSON body, and everything else
// is stored in the metrics column.
func (a *App) setWorkDone(w http.ResponseWriter, r *http.Request, sql string) error {
	workID, err := pathInt(r, "work_id")
	if err != nil {
		return err
	}
	var body map[string]any
	if err := decodeJSONBody(r, &body); err != nil {
		return err
	}

	var stderrFileID, stdoutFileID any
	stderrFileID = body["stderr_file_id"]
	stdoutFileID = body["stdout_file_id"]
	delete(body, "stderr_file_id")
	delete(body, "stdout_file_id")

	metrics, err := httpx.MarshalJSON(body)
	if err != nil {
		return err
	}

	return a.fetchOneJSON(w, r, sql, workID, stderrFileID, stdoutFileID, string(metrics))
}

func (a *App) setWorkFinished(w http.ResponseWriter, r *http.Request) error {
	return a.setWorkDone(w, r, `
        update
            work
        set
            running = false,
            finished = true,
            status = 'finished',
            stderr_file_id = $2,
            stdout_file_id = $3,
            metrics = $4
        where
            work_id = $1
    `)
}

func (a *App) setWorkErrored(w http.ResponseWriter, r *http.Request) error {
	return a.setWorkDone(w, r, `
        update
            work
        set
            running = false,
            failed = true,
            status = 'errored',
            stderr_file_id = $2,
            stdout_file_id = $3,
            metrics = $4
        where
            work_id = $1
    `)
}

func (a *App) getSubprocessInfo(w http.ResponseWriter, r *http.Request) error {
	id, err := pathInt(r, "subprocess_invocation_id")
	if err != nil {
		return err
	}
	return a.fetchOneJSON(w, r, `
        select
            subprocess_invocation_id,
            command_line
        from
            subprocess_invocation
        where
            subprocess_invocation_id = $1
    `, id)
}
