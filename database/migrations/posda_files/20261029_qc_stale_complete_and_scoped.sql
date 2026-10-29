-- Widen and narrow when a draft change marks its QC reviews stale.
--
-- Widen: reviews now complete themselves once every unit is approved, so a
-- complete review must also go stale when its draft's files change --
-- otherwise the publish gate passes on QC that no longer covers the draft.
--
-- Narrow: a review only goes stale for files of the kind it reviews, matching
-- how its units are drawn. A DICOM (full / partial) review covers draft files
-- with a file_series row; a non_dicom review covers files that are not DICOM
-- (coalesce(is_dicom_file, false) = false). Adding a CSV no longer stales the
-- DICOM review, nor a DICOM series the non-DICOM one.
--
-- The function keeps its name so the two triggers on recordset_draft_file
-- (trg_recordset_draft_file_stale_ins / _del) need no change.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

CREATE OR REPLACE FUNCTION public.qc_mark_open_reviews_stale()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  UPDATE public.qc_review q
     SET review_status = 'stale'
   WHERE q.review_status IN ('open', 'complete')
     AND EXISTS (
         SELECT 1
           FROM changed c
           JOIN public.file f ON f.file_id = c.file_id
          WHERE c.recordset_draft_id = q.recordset_draft_id
            AND CASE
                  WHEN q.review_type = 'non_dicom'
                    THEN coalesce(f.is_dicom_file, false) = false
                  ELSE EXISTS (
                    SELECT 1 FROM public.file_series fs WHERE fs.file_id = c.file_id)
                END
     );
  RETURN NULL;
END;
$function$;
