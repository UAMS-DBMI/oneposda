-- Name: FromToStudyMapping
-- Schema: posda_files
-- Columns: ['from_patient_id', 'to_patient_id', 'from_study_instance_uid', 'to_study_instance_uid', 'from_study_date', 'to_study_date']
-- Args: ['activity_id', 'uid_root']
-- Tags: []
-- Description: For a given activity_id, return a list of the mapping
-- between patient_id, study_uid, and study_date.
-- Note that you MUST provide the uid_root
--

select * from ( -- this line required so Posda knows it's a select query
/*
    For a given activity_id, return a list of the mapping
    between patient_id, study_uid, and study_date.

    Note that you must provide the uid_root

*/
with params as (
    select 
        ?::int as activity_id,
        ? as uid_root
), timepoints as (
    select activity_timepoint_id
    from activity_timepoint
    where activity_id = (select activity_id from params)
), timepoint_ends as (
    select
        max(activity_timepoint_id) as max_tp_id,
        min(activity_timepoint_id) as min_tp_id
    from timepoints
), min_studies_intermediate as (
    select distinct
        patient_id as from_patient_id,
        study_instance_uid,
        study_date as from_study_date
    from
        activity_timepoint_file
        natural join file_patient
        natural join file_study
    where activity_timepoint_id = (select min_tp_id from timepoint_ends)
), min_studies as (
    select
        *,
        hash_uid(study_instance_uid, 
                 (select uid_root from params)) as hashed_study_instance_uid
    from min_studies_intermediate
), max_studies as (
    select distinct
        patient_id as to_patient_id,
        study_instance_uid,
        study_date as to_study_date
    from
        activity_timepoint_file
        natural join file_patient
        natural join file_study
    where activity_timepoint_id = (select max_tp_id from timepoint_ends)
)
select
    min_studies.from_patient_id,
    max_studies.to_patient_id,
    min_studies.study_instance_uid as from_study_instance_uid,
    max_studies.study_instance_uid as to_study_instance_uid,
    min_studies.from_study_date,
    max_studies.to_study_date
from max_studies
left join min_studies 
    on max_studies.study_instance_uid = min_studies.hashed_study_instance_uid
) q
;
