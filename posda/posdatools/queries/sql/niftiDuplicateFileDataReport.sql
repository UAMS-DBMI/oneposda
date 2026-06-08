-- Name: niftiDuplicateFileDataReport
-- Schema: posda_files
-- Columns: ['file_id','file_name', 'root_path', 'rel_path']
-- Args: ['activity_id']
-- Tags: ['nifti', 'activity']
-- Description: Provide a list of nifti file_ids with multiple import filenames by activity

select
	   fn.file_id,
       fi.file_name,
       fsr.root_path,
       fl.rel_path
from activity a
join activity_timepoint at2 on a.activity_id = at2.activity_id
join activity_timepoint_file atf on at2.activity_timepoint_id = atf.activity_timepoint_id and  atf.activity_timepoint_id =
               ( select
                    max(activity_timepoint_id) as activity_timepoint_id
                from
                    activity_timepoint
                where
                    activity_id = $1 )
join  file f on f.file_id = atf.file_id
join file_nifti fn on f.file_id = fn.file_id
join file_location fl on fl.file_id = fn.file_id
join file_storage_root fsr on fsr.file_storage_root_id = fl.file_storage_root_id
left join file_import fi on fn.file_id = fi.file_id
and fi.import_event_id = (
    select max(import_event_id)
    from file_import fi_sub
    where fi_sub.file_id = fn.file_id)
right join
		(select id from (select
			fn.file_id as id,
			count(fi.file_name) as c
		from activity a
		join activity_timepoint at2 on a.activity_id = at2.activity_id
		join activity_timepoint_file atf on at2.activity_timepoint_id = atf.activity_timepoint_id and  atf.activity_timepoint_id =
		               ( select
		                    max(activity_timepoint_id) as activity_timepoint_id
		                from
		                    activity_timepoint
		                where
		                    activity_id = $1 )
		join  file f on f.file_id = atf.file_id
		join file_nifti fn on f.file_id = fn.file_id
		join file_location fl on fl.file_id = fn.file_id
		join file_storage_root fsr on fsr.file_storage_root_id = fl.file_storage_root_id
		left join file_import fi on fn.file_id = fi.file_id
		and fi.import_event_id = (
		    select max(import_event_id)
		    from file_import fi_sub
		    where fi_sub.file_id = fn.file_id)
		group by fn.file_id ) as dupes
		where c > 2) repeated on repeated.id = f.file_id;
