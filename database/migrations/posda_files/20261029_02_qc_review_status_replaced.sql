-- Document the 'replaced' QC review status.
--
-- Cloning a stale review now retires the source as 'replaced' rather than
-- leaving it stale, where it would block the publish gate forever. It is
-- terminal and counted like 'cancelled'; only the clone endpoint sets it.
-- review_status is free text with no CHECK constraint, so this only updates
-- the column comment that documents its values.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

COMMENT ON COLUMN "public".qc_review.review_status IS
    'open | complete | cancelled | stale | replaced';
