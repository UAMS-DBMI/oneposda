-- Allow NULL leaf/jaw positions in control_point_bld_position.
--
-- The import parser skips any value longer than skip_large (64 bytes from
-- 2022, 256 since 2025), and MLC leaf positions are usually longer (median
-- ~490 bytes), so they read as NULL. The NOT NULL insert then failed: Perl
-- printed the error and carried on without the row, while the Python worker's
-- atomic import rolls back the whole RT plan. Nothing in Posda reads this
-- column, so store the row with a NULL rather than lose the file.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

ALTER TABLE "public".control_point_bld_position ALTER COLUMN leaf_jaw_positions DROP NOT NULL;
