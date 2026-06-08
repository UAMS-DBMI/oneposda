-- Name: niftiTimePointReport
-- Schema: posda_files
-- Columns: ['file_id','file_name', 'root_path', 'rel_path','magic', 'is_zipped', 'descrip', 'aux_file', 'bitpix', 'datatype', 'num_dim', 'dim1', 'dim2', 'dim3', 'dim4', 'dim5', 'dim6', 'dim7', 'pixdim_0', 'pixdim_1', 'pixdim_2', 'pixdim_3', 'pixdim_4', 'pixdim_5', 'pixdim_6', 'pixdim_7', 'intent_code', 'intent_name', 'intent_p1', 'intent_p2', 'intent_p3', 'cal_max', 'cal_min', 'scl_slope', 'scl_inter', 'slice_start', 'slice_end', 'slice_code', 'sform_code', 'xyzt_units', 's_row_x_0', 's_row_x_1', 's_row_x_2', 's_row_x_3', 's_row_y_0', 's_row_y_1', 's_row_y_2', 's_row_y_3', 's_row_z_0', 's_row_z_1', 's_row_z_2', 's_row_z_3', 'qform_code', 'quatern_b', 'quatern_c', 'quatern_d', 'q_offset_x', 'q_offset_y', 'q_offset_z', 'vox_offset']
-- Args: ['activity_id']
-- Tags: ['nifti', 'activity']
-- Description: Provide a list of nifti files by activity


select
	   fn.file_id,
     fi.file_name,
     fsr.root_path,
     fl.rel_path,
     fn.magic,
     fn.is_zipped,
     fn.descrip,
     fn.aux_file,
     fn.bitpix,
     fn.datatype,
     fn.num_dim,
     fn.dim1,
     fn.dim2,
     fn.dim3,
     fn.dim4,
     fn.dim5,
     fn.dim6,
     fn.dim7,
     fn.pixdim_0,
     fn.pixdim_1,
     fn.pixdim_2,
     fn.pixdim_3,
     fn.pixdim_4,
     fn.pixdim_5,
     fn.pixdim_6,
     fn.pixdim_7,
     fn.intent_code,
     fn.intent_name,
     fn.intent_p1,
     fn.intent_p2,
     fn.intent_p3,
     fn.cal_max,
     fn.cal_min,
     fn.scl_slope,
     fn.scl_inter,
     fn.slice_start,
     fn.slice_end,
     fn.slice_code,
     fn.sform_code,
     fn.xyzt_units,
     fn.s_row_x_0,
     fn.s_row_x_1,
     fn.s_row_x_2,
     fn.s_row_x_3,
     fn.s_row_y_0,
     fn.s_row_y_1,
     fn.s_row_y_2,
     fn.s_row_y_3,
     fn.s_row_z_0,
     fn.s_row_z_1,
     fn.s_row_z_2,
     fn.s_row_z_3,
     fn.qform_code,
     fn.quatern_b,
     fn.quatern_c,
     fn.quatern_d,
     fn.q_offset_x,
     fn.q_offset_y,
     fn.q_offset_z,
     fn.vox_offset
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
order by f.file_id;
