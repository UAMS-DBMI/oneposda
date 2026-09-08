-- Name: InsertIntoDicomEditCompareIdempotent
-- Schema: posda_files
-- Columns: []
-- Args: ['subprocess_invocation_id', 'from_file_digest', 'to_file_digest', 'short_report_file_id', 'long_report_file_id', 'to_file_path']
-- Tags: ['for_scripting', 'dicom_edit']
-- Description: Upserting form of InsertIntoDicomEditCompareFixed.
-- 
-- A compare can now run more than once for the same file, because a worker
-- killed mid-compare has its task reclaimed and redone. The plain insert would
-- add a second row and double-count that file in DifferenceReportByEditId.

insert into dicom_edit_compare (
  subprocess_invocation_id, from_file_digest, to_file_digest,
  short_report_file_id, long_report_file_id, to_file_path
) values ( ?, ?, ?, ?, ?, ? )
on conflict (subprocess_invocation_id, from_file_digest) do update set
  to_file_digest       = excluded.to_file_digest,
  short_report_file_id = excluded.short_report_file_id,
  long_report_file_id  = excluded.long_report_file_id,
  to_file_path         = excluded.to_file_path
