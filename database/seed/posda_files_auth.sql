-- Authorization content for a fresh install.
--
-- This is hand-maintained on purpose. The auth schema in a live database holds
-- real user accounts and password hashes, so it is never dumped into all.sql.
-- A fresh install gets exactly two accounts:
--
--   0  system  used by daemons and background work (added by migration 0024)
--   1  admin   the bootstrap administrator; change its password on first login
--
-- Applications and their permissions are listed in full so that admin can be
-- granted by (app, permission) name rather than by id. Add a row here when an
-- application or permission is introduced; ids are kept in step with the
-- development database so that nothing already granted there shifts.

COPY auth.apps (app_id, app_name) FROM stdin;
1	UserAdmin
2	PosdaCuration
3	PhiFixer
4	ReviewPhi
5	SubmissionSender
6	CountGetter
7	FileDist
8	DicomProxy
9	DicomProxyAnalysis
10	DbIf
11	Kaleidoscope
12	NewItcTools
13	ActivityBasedCuration
\.

SELECT setval('auth.apps_app_id_seq', (SELECT max(app_id) FROM auth.apps), true);

COPY auth.permissions (permission_id, app_id, permission_name) FROM stdin;
1	1	launch
2	2	launch
3	3	launch
4	4	launch
5	5	launch
6	6	launch
7	7	launch
8	8	launch
9	9	launch
10	10	launch
11	1	debug
12	2	debug
13	3	debug
14	4	debug
15	5	debug
16	6	debug
17	7	debug
18	8	debug
19	9	debug
20	10	debug
22	11	launch
23	11	debug
38	10	superuser
44	12	CanDebug
45	12	launch
55	10	curator
56	10	developer
57	10	SrViewer
58	12	IsExpert
59	13	launch
60	13	debug
\.

SELECT setval('auth.permissions_permission_id_seq',
              (SELECT max(permission_id) FROM auth.permissions), true);

COPY auth.users (user_id, user_name, full_name, password, disabled) FROM stdin;
0	system	System Account	\N	f
1	admin	Default Admin Account	aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE	f
\.

SELECT setval('auth.users_user_id_seq', (SELECT max(user_id) FROM auth.users), true);

-- What the bootstrap administrator can do. Granted by name so this list stays
-- correct if permission ids are ever renumbered.
INSERT INTO auth.user_permissions (user_id, permission_id)
SELECT 1, p.permission_id
FROM auth.permissions p
JOIN auth.apps a USING (app_id)
WHERE (a.app_name, p.permission_name) IN (
    ('UserAdmin',             'launch'),
    ('UserAdmin',             'debug'),
    ('DbIf',                  'launch'),
    ('DbIf',                  'debug'),
    ('DbIf',                  'superuser'),
    ('DbIf',                  'curator'),
    ('Kaleidoscope',          'launch'),
    ('Kaleidoscope',          'debug'),
    ('ActivityBasedCuration', 'launch'),
    ('ActivityBasedCuration', 'debug')
);
