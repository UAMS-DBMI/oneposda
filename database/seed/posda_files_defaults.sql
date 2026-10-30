-- Default rows a fresh posda_files needs before any daemon starts.
-- Nothing here comes from a live database; keep it minimal and generic.

-- The file-import daemon's control row; it refuses to start without one.
INSERT INTO public.import_control
    (status, processor_pid, idle_seconds, pending_change_request, files_per_round)
VALUES
    ('waiting to go inservice', NULL, 10, NULL, 50);

-- The admin account's inbox, so background work has somewhere to report.
COPY public.user_inbox (user_inbox_id, user_name, user_email_addr) FROM stdin;
1	admin	admin@admin.bogus
\.

SELECT setval('public.user_inbox_user_inbox_id_seq', 1, true);

-- pg_dump creates materialized views WITH NO DATA, and querying an
-- unpopulated one is an error. Populate every one in public.
DO $$
DECLARE
    mv record;
BEGIN
    FOR mv IN SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
    LOOP
        EXECUTE format('REFRESH MATERIALIZED VIEW public.%I', mv.matviewname);
    END LOOP;
END
$$;
