package routes

import (
	"net/http"

	"tcia/posda-api/internal/httpx"
)

// registerDashboard ports papi/routes/dashboard.py: read-only
// monitoring queries.
func (a *App) registerDashboard(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "test error, not allowed")
	})
	a.public(mux, "GET /v1/dashboard", notAllowed)
	a.public(mux, "GET /v1/dashboard/{$}", notAllowed)

	a.protected(mux, "GET /v1/dashboard/slow_dbif_queries/{days}",
		func(w http.ResponseWriter, r *http.Request) error {
			days, err := pathInt(r, "days")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        select
        	*
        	,(query_end_time - query_start_time)::text  as query_time
        from
        	query_invoked_by_dbif
        where
        	query_end_time is not null
        	and (
        	( extract( day from(current_timestamp - query_end_time))::int < $1 )
        	or ( extract( day from(current_timestamp - query_start_time))::int < $1 )
        	)
        order by query_time desc
        limit 20;
    `, days)
		})

	a.protected(mux, "GET /v1/dashboard/prbs",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select
          subprocess_invocation_id, background_subprocess_id,
          when_script_started, when_background_entered, command_line,
          (now()-when_background_entered)::text as time_in_background,
          background_pid
        from
          subprocess_invocation natural join background_subprocess
        where
          when_background_entered is not null and when_script_ended is null and
          subprocess_invocation_id != 0 and crash is null
        order by subprocess_invocation_id
        limit 20;
    `)
		})

	a.protected(mux, "GET /v1/dashboard/bsbu",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select
         invoking_user
         ,count(subprocess_invocation_id) as count_background
         ,avg(when_script_ended-when_background_entered)::text as avg_time_in_background
        from
          subprocess_invocation natural join background_subprocess
        where
          when_background_entered is not null
          and subprocess_invocation_id != 0
          and crash is null
          and extract(day from(now()- when_background_entered))::int < 7
        group by invoking_user;
    `)
		})

	a.protected(mux, "GET /v1/dashboard/fwt",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select * from files_without_type
        limit 20;
    `)
		})

	a.protected(mux, "GET /v1/dashboard/fwl",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select * from files_without_location
        limit 20;
    `)
		})

	a.protected(mux, "GET /v1/dashboard/ftc",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
    select
    	*
    from
    	file_imports_over_time
    where
    	importyear is not null
    order by
    	importyear
    	,importmonth;
    `)
		})

	a.protected(mux, "GET /v1/dashboard/tla",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
    select pid,
      usename,
      pg_blocking_pids(pid) as blocked_by,
      query as blocked_query
    from pg_stat_activity
    where cardinality(pg_blocking_pids(pid)) > 0;
    `)
		})

	a.protected(mux, "GET /v1/dashboard/qrvi",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
     select
      query_name,
      max(query_start_time)::text  as last_invocation,
      count(query_invoked_by_dbif_id) as num_invocations,
      sum(query_end_time - query_start_time)::text  as total_query_time,
      extract(epoch from avg(query_end_time - query_start_time)) as avg_query_time
    from
      query_invoked_by_dbif
    where extract(day from query_start_time)::int < 31
    group by query_name
    order by avg_query_time  desc
    limit 120;
    `)
		})
}
