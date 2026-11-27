-- Add the Clinical and Translational Data Commons as a transfer destination.
--
-- Current TCIA downloads point to CTDC, and the release ETL records each
-- recordset's destinations, so CTDC needs its own row rather than borrowing
-- General Commons. Like WordPress it has no destination-specific settings
-- table: the release module shows "no destination-specific settings" for any
-- destination its SETTINGS_ENDPOINT map doesn't list, and the API only
-- branches on idc / nbia / wp. Nothing transfers to it yet; that is separate
-- work (the CRDC daemon).
--
-- The id comes from the identity column (the seed migration reset its
-- sequence), and the NOT EXISTS keeps a re-run, or a row added by hand, from
-- making a duplicate. transfer_destination is already in build-all-sql's
-- lookup-table list, so a rebuilt all.sql carries the row.
--
-- No BEGIN/COMMIT -- ./migrate wraps each migration in --single-transaction.

INSERT INTO public.transfer_destination (destination_name, destination_abbr)
SELECT 'Clinical and Translational Data Commons', 'ctdc'
WHERE NOT EXISTS (
    SELECT 1 FROM public.transfer_destination WHERE destination_abbr = 'ctdc');
