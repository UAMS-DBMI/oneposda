package routes

import (
	"fmt"
	"net/http"
	"regexp"

	"tcia/posda-api/internal/httpx"
)

// identifierRe restricts the client-supplied table/column names that
// get interpolated into SQL. The Python version interpolated them
// verbatim; this keeps the flexibility while refusing anything that
// isn't a plain identifier.
var identifierRe = regexp.MustCompile(`^[a-zA-Z_][a-zA-Z0-9_]*$`)

// registerEdits ports papi/routes/edits.py.
func (a *App) registerEdits(mux *http.ServeMux) {
	a.protected(mux, "POST /v1/edits/state", a.setEditState)
}

func (a *App) setEditState(w http.ResponseWriter, r *http.Request) error {
	body := struct {
		EditID        int64  `json:"edit_id"`
		ExpectedState string `json:"expected_state"`
		NewState      string `json:"new_state"`
		TableName     string `json:"table_name"`
		ColumnName    string `json:"column_name"`
	}{
		TableName:  "dicom_edit_compare_disposition",
		ColumnName: "current_disposition",
	}
	if err := decodeJSONBody(r, &body); err != nil {
		return err
	}
	if !identifierRe.MatchString(body.TableName) || !identifierRe.MatchString(body.ColumnName) {
		return httpx.NewError(http.StatusUnprocessableEntity,
			"table_name and column_name must be plain identifiers")
	}

	rows, err := a.DB.Fetch(r.Context(), fmt.Sprintf(`
        update %s
        set %s = $1
        where subprocess_invocation_id = $2
        and %s = $3
        returning subprocess_invocation_id
    `, body.TableName, body.ColumnName, body.ColumnName),
		body.NewState, body.EditID, body.ExpectedState)
	if err != nil {
		return err
	}

	if len(rows) == 0 {
		current, found, err := a.DB.FetchOne(r.Context(), fmt.Sprintf(`
            select %s
            from %s
            where subprocess_invocation_id = $1
        `, body.ColumnName, body.TableName), body.EditID)
		if err != nil {
			return err
		}
		if !found {
			return httpx.NewError(http.StatusNotFound, "Not Found")
		}
		httpx.WriteJSON(w, http.StatusConflict, map[string]any{
			"detail":         "Column was not in expected state",
			"expected_state": body.ExpectedState,
			"actual_state":   current.Values()[0],
		})
		return nil
	}

	w.WriteHeader(http.StatusOK)
	return nil
}
