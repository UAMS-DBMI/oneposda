package routes

import (
	"net/http"

	"tcia/posda-api/internal/httpx"
)

// registerSegs ports papi/routes/segs.py.
func (a *App) registerSegs(mux *http.ServeMux) {
	notAllowed := a.Auth.Middleware(func(w http.ResponseWriter, r *http.Request) error {
		return httpx.NewError(http.StatusUnauthorized, "test error, not allowed")
	})
	a.public(mux, "GET /v1/segs", notAllowed)
	a.public(mux, "GET /v1/segs/{$}", notAllowed)

	a.protected(mux, "GET /v1/segs/find_segs_in_activity/{activity_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "activity_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        select
          file_id,
          root_path || '/' || rel_path as path
        from
          file_storage_root natural join file_location
        where file_id in (
          select distinct file_id
          from dicom_file df natural join activity_timepoint_file
          where
          dicom_file_type = 'Segmentation Storage'
          and activity_timepoint_id = (
            select max(activity_timepoint_id) as activity_timepoint_id
            from activity_timepoint
            where activity_id = $1
          )
        );
        `, id)
		})

	a.protected(mux, "GET /v1/segs/getLatestFileForSop/{sop_instance_uid}",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
        select max(file_id) as file_id
        from file_sop_common
        where sop_instance_uid = $1;
        `, pathStr(r, "sop_instance_uid"))
		})

	a.protected(mux, "GET /v1/segs/getFORfromfile/{file_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "file_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
            select for_uid from file_for ff where file_id  = $1;
        `, id)
		})

	a.protected(mux, "GET /v1/segs/getSeries/{file_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "file_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
            select series_instance_uid
            from file_series
            natural join file
            where file_id = $1;
        `, id)
		})

	a.protected(mux, "PUT /v1/segs/populate_seg_linkages/{file_id}/{seg_id}/{linked_sop_instance_uid}/{linked_sop_class_uid}",
		func(w http.ResponseWriter, r *http.Request) error {
			fileID, err := pathInt(r, "file_id")
			if err != nil {
				return err
			}
			segID, err := pathInt(r, "seg_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
            INSERT INTO public.file_seg_image_linkage
            (file_id, seg_id, linked_sop_instance_uid, linked_sop_class_uid)
            VALUES($1, $2, $3, $4)
            ON CONFLICT (file_id,seg_id) DO UPDATE SET
              linked_sop_instance_uid=EXCLUDED.linked_sop_instance_uid,
              linked_sop_class_uid=EXCLUDED.linked_sop_class_uid;
            `, fileID, segID,
				pathStr(r, "linked_sop_instance_uid"),
				pathStr(r, "linked_sop_class_uid"))
		})
}
