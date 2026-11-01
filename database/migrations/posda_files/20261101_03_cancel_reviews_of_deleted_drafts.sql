-- Cancel the unfinished QC reviews of drafts that were already deleted.
--
-- Deleting a draft is a soft delete (draft_status = 'deleted') and used to
-- leave its reviews alone, so open and stale reviews of a deleted draft stayed
-- in the pickup queue, "My QC Queue", claims and the cycle rollup. The delete
-- endpoint now cancels them; this brings existing data in line. Complete
-- reviews are left as the record of finished work.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

UPDATE "public".qc_review r
SET review_status = 'cancelled',
    when_updated = now()
FROM "public".recordset_draft d
WHERE d.recordset_draft_id = r.recordset_draft_id
  AND d.draft_status = 'deleted'
  AND r.review_status IN ('open', 'stale');
