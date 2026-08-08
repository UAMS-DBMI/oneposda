package routes

import (
	"net/http"
	"strconv"

	"tcia/posda-api/internal/httpx"
)

// registerPathology ports papi/routes/pathology.py.
//
// Note on the PUT endpoints: the Python handlers run their INSERT/UPDATE
// via db.fetch and then require at least one returned row. Statements
// without a RETURNING clause never return rows, so those endpoints
// perform their write and then respond 422 "Error updating edit status"
// even on success. That behavior is preserved here because existing
// clients depend on it.
func (a *App) registerPathology(mux *http.ServeMux) {
	a.protected(mux, "GET /v1/pathology/start/{vr_id}", a.pathQueryInt("vr_id", `
        select distinct
          path_file_id
        from
          pathology_visual_review_files
        where
          pathology_visual_review_instance_id = $1
        order by path_file_id;
    `))

	a.protected(mux, "GET /v1/pathology/preview_file_name/{pathid}", a.pathQueryInt("pathid", `
         select
            file_name, good_status
        from
            file_import a
            left join pathology_visual_review_status b on a.file_id = b.path_file_id
        where
            a.file_id = $1
             `))

	a.protected(mux, "GET /v1/pathology/preview/{pathid}/{gammaIndex}",
		func(w http.ResponseWriter, r *http.Request) error {
			pathid, err := pathInt(r, "pathid")
			if err != nil {
				return err
			}
			gammaIndex, err := pathInt(r, "gammaIndex")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        select
         distinct preview_file_id
        from
        	pathology_visual_review_preview_files
        where
        	path_file_id = $1
            and gammaindex = $2
        `, pathid, gammaIndex)
		})

	queuedRemovals := httpx.HandlerFunc(func(w http.ResponseWriter, r *http.Request) error {
		return a.fetchJSON(w, r, `
         select
 		file_id
        from pathology_edit_queue p
        where p.status = 'waiting' and p.edit_type = '4';
        `)
	})
	a.protected(mux, "GET /v1/pathology/get_queued_removals", queuedRemovals)
	a.protected(mux, "GET /v1/pathology/get_queued_removals/{$}", queuedRemovals)

	a.protected(mux, "GET /v1/pathology/getActEdits/{act_id}", a.pathQueryInt("act_id", `
        select
            atf.file_id, count(p.status)
        from activity_timepoint_file atf
            left join pathology_edit_queue p on atf.file_id = p.file_id and p.status = 'waiting'
        where atf.activity_timepoint_id =
               ( select
                    max(activity_timepoint_id) as activity_timepoint_id
                from
                    activity_timepoint
                where
                    activity_id = $1 )
        group by atf.file_id
        `))

	a.protected(mux, "GET /v1/pathology/getActEditsByPVRID/{pvr_id}", a.pathQueryInt("pvr_id", `
        select
            atf.file_id as file, count(p.status) as count
        from activity_timepoint_file atf
            left join pathology_edit_queue p on atf.file_id = p.file_id and p.status = 'waiting'
        where atf.activity_timepoint_id =
           (select
                max(activity_timepoint_id) as activity_timepoint_id
            from
                activity_timepoint
            where
                activity_id =
                (select
                    activity_creation_id
                from pathology_visual_review_instance pvri
                where pvri.pathology_visual_review_instance_id = $1 ))
         group by atf.file_id;
        `))

	a.protected(mux, "PUT /v1/pathology/set_edit/{pathid}/{good_status}/{user}",
		func(w http.ResponseWriter, r *http.Request) error {
			pathid, err := pathInt(r, "pathid")
			if err != nil {
				return err
			}
			status, err := parsePathBool(pathStr(r, "good_status"))
			if err != nil {
				return err
			}
			return a.pathEditWrite(w, r, `
        INSERT INTO pathology_visual_review_status
        VALUES($1 , $2, $3, now());
        `, pathid, status, pathStr(r, "user"))
		})

	a.protected(mux, "PUT /v1/pathology/remM/{pathid}", a.pathEditByID(`
        INSERT INTO pathology_edit_queue
        (file_id,edit_type, edit_details, status)
        VALUES($1 , 1, NULL, 'waiting');
        `))

	a.protected(mux, "PUT /v1/pathology/redact/{dims}/{pathid}",
		func(w http.ResponseWriter, r *http.Request) error {
			pathid, err := pathInt(r, "pathid")
			if err != nil {
				return err
			}
			return a.pathEditWrite(w, r, `
        INSERT INTO pathology_edit_queue
        (file_id,edit_type, edit_details, status)
        VALUES($1 , 5, $2, 'waiting');
        `, pathid, pathStr(r, "dims"))
		})

	a.protected(mux, "PUT /v1/pathology/remL/{pathid}", a.pathEditByID(`
        INSERT INTO pathology_edit_queue
        (file_id,edit_type, edit_details, status)
        VALUES($1 , 2, NULL, 'waiting');
        `))

	a.protected(mux, "PUT /v1/pathology/removeF/{pathid}", a.pathEditByID(`
        INSERT INTO pathology_edit_queue
        (file_id,edit_type, edit_details, status)
        VALUES($1 , 4, NULL, 'waiting');
        `))

	a.protected(mux, "PUT /v1/pathology/editMeta/{pathid}", a.pathEditByID(`
        INSERT INTO pathology_edit_queue
        (file_id,edit_type, edit_details, status)
        VALUES($1 , 3, 'imgdesc', 'waiting');
        `))

	a.protected(mux, "PUT /v1/pathology/cancelEdit/{pathid}", a.pathEditByID(`
        update pathology_edit_queue
        set status = 'canceled'
        where
        status = 'waiting'
        and file_id = $1
        `))

	a.protected(mux, "GET /v1/pathology/review/{vr_id}", a.pathQueryInt("vr_id", `
    select distinct
        d.file_name,
        good_status
    from
        pathology_visual_review_preview_files b
        left join file_import d on d.file_id = b.path_file_id
        left join pathology_visual_review_status c on b.path_file_id = c.path_file_id
    where
        pathology_visual_review_instance_id = $1
      `))

	a.protected(mux, "PUT /v1/pathology/copymapping/{oldfile_id}/{newfile_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			oldID, err := pathInt(r, "oldfile_id")
			if err != nil {
				return err
			}
			newID, err := pathInt(r, "newfile_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        	insert into pathology_patient_mapping
            (file_id,patient_id,collection_name,site_name,study_name,image_id,clinical_trial_subject_id)
        select
           $2, patient_id,collection_name,site_name,study_name,image_id,clinical_trial_subject_id
        from
            pathology_patient_mapping a
        where
            a.file_id = $1;
             `, oldID, newID)
		})

	a.protected(mux, "GET /v1/pathology/mapping/{file_id}", a.pathQueryInt("file_id", `
         select
            patient_id
        from
            pathology_patient_mapping a
        where
            a.file_id = $1
             `))

	a.protected(mux, "PUT /v1/pathology/setmapping/{file_id}/{patient_id}/{collection_name}/{site_name}/{study_name}/{image_id}/{clinical_trial_subject_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			fileID, err := pathInt(r, "file_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
        insert into pathology_patient_mapping
            (file_id,patient_id,collection_name,site_name,study_name,image_id,clinical_trial_subject_id)
        VALUES
            ($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (file_id) DO UPDATE
        set
            patient_id=$2,
            collection_name=$3,
            site_name=$4,
            study_name=$5,
            image_id=$6,
            clinical_trial_subject_id=$7
             `, fileID,
				pathStr(r, "patient_id"), pathStr(r, "collection_name"),
				pathStr(r, "site_name"), pathStr(r, "study_name"),
				pathStr(r, "image_id"), pathStr(r, "clinical_trial_subject_id"))
		})

	a.protected(mux, "GET /v1/pathology/image_desc/{file_id}", a.pathQueryInt("file_id", `
        select
            layer_id, image_desc
        from
            pathology_image_description a
        where
            a.file_id = $1
             `))

	a.protected(mux, "GET /v1/pathology/getcount",
		func(w http.ResponseWriter, r *http.Request) error {
			// Python counts a module-level dict that is never written to.
			return httpx.JSON(w, 0)
		})

	a.protected(mux, "GET /v1/pathology/find_files/{activity_id}", a.pathQueryInt("activity_id", `
        select f.file_id from file f join activity_timepoint_file atf  on f.file_id = atf.file_id
            where atf.activity_timepoint_id in (
                select
                    max(activity_timepoint_id) as activity_timepoint_id
                from
                    activity_timepoint
                where
                    activity_id = $1
              );
        `))

	a.protected(mux, "GET /v1/pathology/find_edits/{file_id}", a.pathQueryInt("file_id", `
     select pathology_edit_queue_id, edit_type, edit_details
            from pathology_edit_queue
             where
                 file_id = $1
                 and status = 'waiting'
    `))

	a.protected(mux, "GET /v1/pathology/find_relpath/{file_id}", a.pathQueryInt("file_id", `
      select root_path, rel_path
      from file_location f
      natural join file_storage_root fsr
      where f.file_id = $1
     `))

	a.protected(mux, "PATCH /v1/pathology/completeEdit/{edit_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			editID, err := pathInt(r, "edit_id")
			if err != nil {
				return err
			}
			rows, err := a.DB.Fetch(r.Context(), `
        update pathology_edit_queue set status = 'complete' where pathology_edit_queue_id = $1 returning pathology_edit_queue_id;
        `, editID)
			if err != nil {
				return err
			}
			if len(rows) < 1 {
				return httpx.NewError(http.StatusUnprocessableEntity,
					"Complete Edit: Error updating edit status")
			}
			return httpx.JSON(w, map[string]any{"status": "success"})
		})

	a.protected(mux, "GET /v1/pathology/getXfiles/{import_id}/{file_type}",
		func(w http.ResponseWriter, r *http.Request) error {
			importID, err := pathInt(r, "import_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
            select
                file_id
            from
                file_import
            where
                import_event_id = $1
                AND SUBSTRING(file_name FROM '\.([^\.]*)$') = $2;
            `, importID, pathStr(r, "file_type"))
		})

	a.protected(mux, "GET /v1/pathology/get_files_from_import/{import_id}", a.pathQueryInt("import_id", `
            select
                file_id
            from
                file_import
            where
                import_event_id = $1;
            `))

	a.protected(mux, "PUT /v1/pathology/create_path_activity/{activity_name}/{user}",
		func(w http.ResponseWriter, r *http.Request) error {
			return a.fetchJSON(w, r, `
            insert into activity (
                brief_description,
                when_created,
                who_created
            ) values (
             $1 ,now(), $2)
             returning activity_id;
            `, pathStr(r, "activity_name"), pathStr(r, "user"))
		})

	a.protected(mux, "PUT /v1/pathology/create_path_activity_timepoint/{activity_id}/{user}",
		func(w http.ResponseWriter, r *http.Request) error {
			id, err := pathInt(r, "activity_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
            insert into activity_timepoint(
                activity_id,
                when_created,
                who_created,
                comment,
                creating_user
            ) values (
                $1, now(), $2, 'Post Edit Pathology TP', $2)
            returning activity_timepoint_id;
            `, id, pathStr(r, "user"))
		})

	a.protected(mux, "PUT /v1/pathology/add_file_to_path_activity_timepoint/{atf_id}/{file_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			atfID, err := pathInt(r, "atf_id")
			if err != nil {
				return err
			}
			fileID, err := pathInt(r, "file_id")
			if err != nil {
				return err
			}
			return a.fetchJSON(w, r, `
                    insert into activity_timepoint_file(
                         activity_timepoint_id,
                         file_id
                        ) values (
                          $1, $2)
                    returning file_id;
                    `, atfID, fileID)
		})

	a.protected(mux, "PUT /v1/pathology/bulkMacro/{pathology_visual_review_instance_id}",
		a.pathBulkEdit("1"))
	a.protected(mux, "PUT /v1/pathology/bulkLabel/{pathology_visual_review_instance_id}",
		a.pathBulkEdit("2"))
	a.protected(mux, "PUT /v1/pathology/bulkMeta/{pathology_visual_review_instance_id}",
		a.pathBulkEdit("3"))

	a.protected(mux, "PUT /v1/pathology/recordPathDBresponse/{file_id}/{node_id}",
		func(w http.ResponseWriter, r *http.Request) error {
			fileID, err := pathInt(r, "file_id")
			if err != nil {
				return err
			}
			return a.pathEditWrite(w, r, `
        INSERT INTO pathology_path_db_linkage
        (file_id,node_id,upload_time)
        VALUES($1 , $2, now());
        `, fileID, pathStr(r, "node_id"))
		})

	a.protected(mux, "PUT /v1/pathology/insert_image_meta/{file_id}/{format}/{modality}/{protocol}/{manufacturer}/{model}/{xResolution}/{yResolution}/{resolutionUnit}/{magnification}/{mppx}/{mppy}/{image_volume_width}/{image_volume_height}/{reference_pixel_physical_value_x}/{reference_pixel_physical_value_y}",
		a.insertImageMeta)
}

// pathQueryInt builds a handler for the "one int path param, one
// query" endpoints that dominate this module.
func (a *App) pathQueryInt(param, sql string) httpx.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		id, err := pathInt(r, param)
		if err != nil {
			return err
		}
		return a.fetchJSON(w, r, sql, id)
	}
}

// pathEditWrite performs a write and then responds exactly like the
// Python `len(record) < 1` check: statements without RETURNING yield
// no rows, so the response is a 422 even though the write succeeded.
func (a *App) pathEditWrite(w http.ResponseWriter, r *http.Request, sql string, args ...any) error {
	rows, err := a.DB.Fetch(r.Context(), sql, args...)
	if err != nil {
		return err
	}
	if len(rows) < 1 {
		return httpx.NewError(http.StatusUnprocessableEntity, "Error updating edit status")
	}
	return httpx.JSON(w, map[string]any{"status": "success"})
}

func (a *App) pathEditByID(sql string) httpx.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		pathid, err := pathInt(r, "pathid")
		if err != nil {
			return err
		}
		return a.pathEditWrite(w, r, sql, pathid)
	}
}

func (a *App) pathBulkEdit(editType string) httpx.HandlerFunc {
	sql := `
   INSERT INTO pathology_edit_queue
 			(file_id,edit_type, edit_details, status)
        	select
	            file_id,  ` + editType + `, NULL, 'waiting'
	        from activity_timepoint_file atf
	        where atf.activity_timepoint_id =
	               ( select
	                    max(activity_timepoint_id) as activity_timepoint_id
	                from
	                    activity_timepoint att
	                    join pathology_visual_review_instance pf
	                	on att.activity_id = pf.activity_creation_id
	                	where pf.pathology_visual_review_instance_id = $1 );
    `
	return func(w http.ResponseWriter, r *http.Request) error {
		id, err := pathInt(r, "pathology_visual_review_instance_id")
		if err != nil {
			return err
		}
		return a.pathEditWrite(w, r, sql, id)
	}
}

func parsePathBool(s string) (bool, error) {
	switch s {
	case "1", "true", "True", "yes", "on":
		return true, nil
	case "0", "false", "False", "no", "off":
		return false, nil
	}
	return false, httpx.NewError(http.StatusUnprocessableEntity,
		"good_status must be a boolean")
}

func (a *App) insertImageMeta(w http.ResponseWriter, r *http.Request) error {
	fileID, err := pathInt(r, "file_id")
	if err != nil {
		return err
	}
	floats := map[string]float64{}
	for _, name := range []string{
		"mppx", "mppy", "image_volume_width", "image_volume_height",
		"reference_pixel_physical_value_x", "reference_pixel_physical_value_y",
	} {
		f, err := parsePathFloat(r, name)
		if err != nil {
			return err
		}
		floats[name] = f
	}

	return a.fetchOneJSON(w, r, `
        INSERT INTO public.pathology_image_meta
        (file_id,
        format,
        modality,
        protocol,
        manufacturer,
        model,
        xresolution,
        yresolution,
        resolutionunit,
        magnification,
        mppx,
        mppy,
        image_volume_width,
        image_volume_height,
        reference_pixel_physical_value_x,
        reference_pixel_physical_value_y)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        RETURNING file_id;
        `, fileID,
		pathStr(r, "format"), pathStr(r, "modality"), pathStr(r, "protocol"),
		pathStr(r, "manufacturer"), pathStr(r, "model"),
		pathStr(r, "xResolution"), pathStr(r, "yResolution"),
		pathStr(r, "resolutionUnit"), pathStr(r, "magnification"),
		floats["mppx"], floats["mppy"],
		floats["image_volume_width"], floats["image_volume_height"],
		floats["reference_pixel_physical_value_x"],
		floats["reference_pixel_physical_value_y"])
}

func parsePathFloat(r *http.Request, name string) (float64, error) {
	f, err := strconv.ParseFloat(r.PathValue(name), 64)
	if err != nil {
		return 0, httpx.NewError(http.StatusUnprocessableEntity,
			"path parameter \""+name+"\" must be a number")
	}
	return f, nil
}
