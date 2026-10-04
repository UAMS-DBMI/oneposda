-- Unique indexes for the ingest pipeline's shared lookup tables.
--
-- Required by the posda.ingest lookup_upsert fix (POSDA_INGEST_FIX_LOOKUP_UPSERT).
--
-- These three tables are populated with check-then-insert and no unique
-- constraint. With the production five workers running concurrently, two
-- can miss the same row and both insert it. Confirmed in the dev database:
-- slope_intercept held 4 rows of which only 1 was distinct, and
-- window_level held 5 rows of which 3 were distinct.
--
-- NULLS NOT DISTINCT is essential: si_units and win_lev_desc are NULL for
-- most rows, and under the default NULLS DISTINCT every such row would be
-- considered unique and the constraint would prevent nothing. It requires
-- PostgreSQL 15 or later (the deployment runs 18).
--
-- Deduplicates before creating the indexes, remapping any references first.
-- ./migrate runs this in a single transaction, so a failure leaves nothing
-- half-applied.

-- slope_intercept ---------------------------------------------------------
create temporary table si_map as
select
  slope_intercept_id as old_id,
  min(slope_intercept_id) over (
    partition by slope, intercept, si_units
  ) as new_id
from slope_intercept;

update image_slope_intercept t
set slope_intercept_id = m.new_id
from si_map m
where t.slope_intercept_id = m.old_id and m.old_id <> m.new_id;

update file_slope_intercept t
set slope_intercept_id = m.new_id
from si_map m
where t.slope_intercept_id = m.old_id and m.old_id <> m.new_id;

delete from slope_intercept s
using si_map m
where s.slope_intercept_id = m.old_id and m.old_id <> m.new_id;

create unique index if not exists slope_intercept_natural_key
  on slope_intercept (slope, intercept, si_units) nulls not distinct;

-- window_level ------------------------------------------------------------
create temporary table wl_map as
select
  window_level_id as old_id,
  min(window_level_id) over (
    partition by window_width, window_center, win_lev_desc
  ) as new_id
from window_level;

update image_window_level t
set window_level_id = m.new_id
from wl_map m
where t.window_level_id = m.old_id and m.old_id <> m.new_id;

update file_win_lev t
set window_level_id = m.new_id
from wl_map m
where t.window_level_id = m.old_id and m.old_id <> m.new_id;

delete from window_level w
using wl_map m
where w.window_level_id = m.old_id and m.old_id <> m.new_id;

create unique index if not exists window_level_natural_key
  on window_level (window_width, window_center, win_lev_desc) nulls not distinct;

-- unique_pixel_data -------------------------------------------------------
-- Empty in every database inspected, because skip_large stops ImagePixel
-- ever reaching it, so no deduplication step is needed here.
create unique index if not exists unique_pixel_data_natural_key
  on unique_pixel_data (digest, size);
