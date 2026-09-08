\connect posda_files
--
-- PostgreSQL database dump
--

\restrict mSgwALpYGku8jHAyVF4SFoL8l2nVlooKhvfKbo9ZpEsHlnSJhYKbIF0IVngs7OH

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: apps; Type: TABLE DATA; Schema: auth; Owner: -
--

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
12	NewItcTools
11	Kaleidoscope
13	ActivityBasedCuration
\.


--
-- Data for Name: permissions; Type: TABLE DATA; Schema: auth; Owner: -
--

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
44	12	CanDebug
22	11	launch
23	11	debug
38	10	superuser
58	12	IsExpert
59	13	launch
60	13	debug
45	12	launch
49	10	legacy_bbennett
50	10	legacy_ksmith01
51	10	legacy_priorf
52	10	legacy_rddobbins
53	10	legacy_smberryman
54	10	legacy_tracyn
55	10	curator
56	10	developer
57	10	SrViewer
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: auth; Owner: -
--

COPY auth.users (user_id, user_name, full_name, password, disabled) FROM stdin;
1	admin	Default Admin Account	enporpr5,VEk2qinCPF8jO0im8PM4m0U8E8TD6el/DWJ3z07b2qk	f
18	gblake		KrKfeGBq,f0lf8ZnWPCJPagRKJgTgak5DnOH7VUw/fEPcXCtHeX0	f
19	angeluspa		dL2VjOry,6tp/ByprNtXv360JAppnLorRHRoiR6Ze2PHYwVAe7Ww	f
6	tracyn		giLMzJkd,ZuKHOphrA6Tg0caqbfbEK1fbZPKW6b2xIKxfd+52PWs	f
26	sullyb		IVcO2gB1,YGL5irUHuqwity437kx8A8BEMABApsMg/ojmfwsD3yM	f
21	bcamp		Mb8Rk2WK,2iDGHuHDymsU9xljjAZ3RxBdP9UtKpNAh8qzHg+v1FM	f
17	levineb		5u1Gx8fS,SqxwFUiDgubifjP5H30jvlvalQlQgAjebfBwgASYdSg	f
16	ebilello		5Brtle09,pefDe0cSt4GTQpEMMlUshSIZJzZ5a09bepSmiOXBuxw	f
28	mwruthe		dWW9hnqj,Ydfw7vk0XcarAPaIvzGrtbIy+66uf8XJnJJjHR53AH4	f
23	nhonomichl		QbwYLBvR,xi0x5CX6GPnlbJoGzbFX5XnIk1nguyieZ7EC13V94bQ	f
32	haydex		xbuSz72y,xpRldz4148p1tVCJVRNxiN5+0uhtL5MyQymr5Sa+rxU	f
4	ksmith01		y6LxzOxE,8a+zSSrkcs2CbPDhlrYQTaKDcnQUrhk5Bu8pIWPApns	f
0	system	System Account	xpQKnBp4,7Gc0J3D9rRulU4SmEXak5pMi6NjyN0v6LB5AXQ22XFM	f
2	quasarj	Quasar Jarosz	wKXyWRZi,DHKO9IkOasb89+Cvj3LHsyGTthxz54lmUelM+dIc5Gk	f
8	priorf		afyyQxek,1b6jcfa4e/2RusEF9e4+au+ATCLpRywS23fh7pcAge4	f
11	rddobbins		vD/XGyYF,q49lvcv9gREflv1VojEIS0L7iHtc2erQtchCSnWclws	f
12	jfrund		K63BGZQb,wyGrRhuKzpCMu9ewswYbLkvSZkn7608YnPab5iINgKI	f
13	jpbona	Jonathan Bona	gfTxAyKW,lGMCeTsA52R3IclGG6BtSYfW8Lcb9BYRUwR4SxLL5zY	f
15	sutecht		s3zyKU.q,OExY7I5e/l5NLFYMWsfHf4YPZGcuKStMs2lSN0m7v2Q	f
20	hurveyce		R5TCUTZ4,u68RLev3fyWActkAyFcvmyQIjcVs2NTPqAEhCeuJFmc	f
29	pfarmer		PevrKDJY,HvfuTBoSDFDB0gbEw8c9Uo11NTbmoB1YahzwZJIfOfA	f
30	abergeman		Sj5yOlTq,HcCdjzXDOl80MT2Qw5niG75b8o9DRoACObA0oFqFYAU	f
\.


--
-- Data for Name: user_permissions; Type: TABLE DATA; Schema: auth; Owner: -
--

COPY auth.user_permissions (user_id, permission_id) FROM stdin;
11	22
11	52
11	10
11	59
11	55
26	59
26	10
6	55
6	22
6	59
6	57
6	10
6	54
6	20
29	59
32	49
26	55
32	55
32	56
26	56
32	10
26	60
23	55
\N	20
\N	2
\N	12
23	38
\N	10
23	1
23	59
23	60
13	57
13	55
13	10
2	38
2	10
2	45
2	6
2	3
15	55
23	49
23	56
6	23
21	22
21	55
15	44
15	10
15	22
21	56
15	11
21	59
15	56
21	57
21	10
18	60
18	56
18	10
18	1
12	20
12	22
12	56
12	55
18	38
18	59
18	55
12	10
15	59
15	45
23	10
15	1
15	23
23	11
2	12
28	59
4	20
8	20
8	6
8	16
8	2
4	45
4	59
8	51
4	10
8	12
8	10
15	58
15	20
15	60
28	1
28	10
28	56
28	55
15	49
28	49
30	59
2	56
2	58
2	23
2	5
2	1
2	20
2	2
2	44
2	55
2	13
2	22
2	59
2	60
4	44
4	55
4	38
4	22
4	50
4	1
4	5
20	56
20	55
20	10
20	59
20	22
19	55
19	56
19	22
19	10
19	59
16	10
16	59
16	22
16	56
16	55
17	10
17	59
17	22
17	55
17	56
1	59
1	20
1	11
1	1
1	10
32	59
\.


--
-- Data for Name: migration; Type: TABLE DATA; Schema: db_version; Owner: -
--

COPY db_version.migration (filename, sha256, applied_at, applied_by) FROM stdin;
0001_add_key_to_subprocess_invocation.sql	cdc19c443e072fec029c4d89333e5cfe35262e28fb8c68f7fa51e754b9c897bf	2026-08-12 21:16:44.28909+00	postgres
0002_create_public_copy_status_table.sql	2279ba0d074439479f256af703b83a3721f82f67316634e0c369ad4f33c033c6	2026-08-12 21:16:44.316941+00	postgres
0003_create_button_popularity_table.sql	914c27505e366037710d8edd9a21c16cbab9b3dfd4c8b35cb2e1471076c0d1a7	2026-08-12 21:16:44.344762+00	postgres
0004_add_third_party_analysis_to_activity.sql	555d9b863e3720c110b12a2d544a361e30864b5b5fa2e8ebe902c0c377719fc9	2026-08-12 21:16:44.372355+00	postgres
0005_create_submissions_table.sql	7e4e90e396b542e34d6624d37f5f1f48e1c5bbb689c6ed2f25c84c0ad3fe6660	2026-08-12 21:16:44.396147+00	postgres
0006_drop_not_null_on_modality.sql	e6d4f10640da0c6bce45ba72ded18ff06070391588a92619bfff6a5820b02d93	2026-08-12 21:16:44.421513+00	postgres
0007_add_origin_to_import_event.sql	696879f3c9765cc6adfdcace55354057c794084699456b0dfbbfe0e79bb2ee8e	2026-08-12 21:16:44.447174+00	postgres
0008_add_expected_count_to_import_event.sql	8e8be6b3bf679f375e352121c2ea035348ccdd5efceb39b97dc38484e4407851	2026-08-12 21:16:44.471955+00	postgres
0009_create_export_event_related_tables.sql	9b16295dbaf0722c008fa058740530cc48d8f74b001286bbf69ac2db54754f11	2026-08-12 21:16:44.500048+00	postgres
0010_add_outdated_to_spreadsheet_operation.sql	46de81148d789b5f0f30ad2dd21c0e6f93e9e8034809db884dba504ae8076e8f	2026-08-12 21:16:44.526815+00	postgres
0011_set_oudated_operations.sql	3bd39ac4b247a4353660555f786607ad1fa65007f80e59d3474064e3a54c9288	2026-08-12 21:16:44.552061+00	postgres
0012_create_work_table.sql	4c025aefe456a2c3d866688c9f57feb3f2c72549a68812ac770f11f2cb6841a5	2026-08-12 21:16:44.58019+00	postgres
0013_dup_sops_comparison.sql	ea6d63c831f18c533423af279e3d54366812df3353451f64c8513ec0af96cd53	2026-08-12 21:16:44.607503+00	postgres
0014_add_priority_to_spreadsheet_operation.sql	643c583a54a6b03a271942303b4eb1da03700edb6356c08f016dca4ff110ff0c	2026-08-12 21:16:44.633303+00	postgres
0015_add_queue_name_to_work.sql	9be6802431b1a49090188843a203555b31894f26232350692bbf80cf4e7d7377	2026-08-12 21:16:44.659515+00	postgres
0016_struct_contours_to_slice.sql	9d39df9698780687e0dc29d837d600f34d684537cf129503ebaccbd31c14e1f9	2026-08-12 21:16:44.689224+00	postgres
0017_add_metrics_to_work.sql	e58f3eb57265bafd38081c41b05e20d9d68f6bcbb0b45845252dc30bd05187df	2026-08-12 21:16:44.717957+00	postgres
0018_add_png_to_seg_slice_bitmap_file.sql	a053f15bfb2f22f38ef649706910583f42f69bdbee1c3198381134df4c49c6cd	2026-08-12 21:16:44.745193+00	postgres
0019_file_nifti.sql	7053c5bff228b31d9486141b49fc410b6735e536b9233f0ef7a75dcfc3ce166f	2026-08-12 21:16:44.772214+00	postgres
0020_fix_file_nifti.sql	e3eae03bfffc63fedcbb6434385e8c26537ce1981e438fe5288f03d66eed1595	2026-08-12 21:16:44.798821+00	postgres
0021_create_new_nifti_defacing.sql	70e40f87926e8a9b6d1451c1c4495d91d3039f01ab0c85c7cb2f61b29559117d	2026-08-12 21:16:44.825949+00	postgres
0022_move_auth_to_files.sh	b67a2e896d8fffbc852185ff723c45c970d31e00b3eec7a7fa3b71e52ad7c4ec	2026-08-12 21:16:44.853405+00	postgres
0023_add_disabled_to_users.sql	ee040c3ff1ce84f135aa0a4ff45bd31471f6109bae6cad3f33838fea8ae5a260	2026-08-12 21:16:44.879512+00	postgres
0024_add_system_user.sql	08cbcdda324d7c7519716297903e3a69970a6c9d0841b6322c25372b546a2d26	2026-08-12 21:16:44.906632+00	postgres
0025_add_result_to_deface.sql	b8ee8a742cda1079d1b792cee6417e9e61c0f227b5640bebc5c55c8581795fe0	2026-08-12 21:16:44.933925+00	postgres
0026_add_success_to_deface.sql	53273b8e1a52df747f407cf47df3253e618ef476c563020da5340ea03c794191	2026-08-12 21:16:44.960081+00	postgres
0027_bad_contour_to_bitmap.sql	9445d9dfca4e3dae565ee35b26f6e2b631282df154435140acd7e6e21a7addd2	2026-08-12 21:16:44.987061+00	postgres
0028_create_dicom_slice_nifti_slice.sql	3668a24a47e29c159bde8e16e43930a9a43a9d6027a8d7209608baaf32b08353	2026-08-12 21:16:45.015394+00	postgres
0029_create_file_nifti_defacing.sql	0026581134d8191dd1e32507364fc5be2aa267fbecc4e28c6cbaee5385d5484c	2026-08-12 21:16:45.043031+00	postgres
0030_create_nifti_jpegs.sql	15fd22aa2dadfb2e9b9091594714800ff55d6674e55a734a66ef76ac10d24776	2026-08-12 21:16:45.070376+00	postgres
0031_create_query_log_table.sql	0ad7565f628c9a6e806eeddfa08d94c2dfae686ccaca75ba42142a3a87583d7a	2026-08-12 21:16:45.096252+00	postgres
0032_deleteWhatHasQueries.sql	9dc88ada8cced1da08a2e7c5ab4e092f33168269884dd14e181b1c0561eb7987	2026-08-12 21:16:45.122172+00	postgres
0033_nifti_projection_review.sql	9cfe8d99ce67a2166520f8ccb58aff26e69d3d8b93914ea52491e4591e171869	2026-08-12 21:16:45.148735+00	postgres
0034_seg_bitmap.sql	4ce1cd3f4f5cefae38eec000cb4bba4944075f320409fec8b5eff8aeab0c40d3	2026-08-12 21:16:45.175984+00	postgres
0035_series_to_nifti.sql	3577e28a446f9280a12e3d9c89667022459453724436dc7f7b9d6a2236d2735d	2026-08-12 21:16:45.202495+00	postgres
0036_create_dcm4chee_copy.sql	c6f425b09db670a07b8ecbf4f5eaa87c6e1ae4643df0b66745de7d95da5755b2	2026-08-12 21:16:45.226249+00	postgres
0037_add_grouping_tables.sql	62377777fbf9362142d385ddf4c5c5493fb85a2b2c6f97daf0399de79e5578c5	2026-08-12 21:16:45.253411+00	postgres
0038_fix_file_nifti2.sql	607e0d70cef0e4cf3afcf5e637402dbe444e19ca5b62be3934664a1d061ddeaa	2026-08-12 21:16:45.280958+00	postgres
0039_add_file_name_table.sql	48a709efb0fa50c0eabbde1cce317ffa28c9915e29c55837821943caee0be295	2026-08-12 21:16:45.309341+00	postgres
0040_add_nifti_visual_review.sql	56f68734b433725929207cfda810e0cf48d4544f15aa0ec16c63db471fbc6271	2026-08-12 21:16:45.338827+00	postgres
0041_add_masking_tables.sql	582e1705b3a3977cfec5a21b0756c258793eacf165854354cd1acad5671b3c20	2026-08-12 21:16:45.366741+00	postgres
0042_add_values_to_masking_status_type.sql	1f8f0a0aa56d5d18f55b155749e4011d6e43ac3f99d857850b8ead7b193e2295	2026-08-12 21:16:45.393088+00	postgres
0043_add_uid_root_to_submissions.sql	a6ffb8270ece1f54ff0efbabea2446a2e0be652dec8f750196cbe953d6c7edd2	2026-08-12 21:16:45.420043+00	postgres
0044_path_migration_master.sql	c5ad7eb4886b90f71f74077897d1e8772eabc62ec504c1e5f99e3d515be584fa	2026-08-12 21:33:02.930184+00	postgres
0045_remove_roi_for_uid_not_null_constraint.sql	fe531b0971ca54b6d4c7bd07aac9562f5108f75a49001c52794393b8502e8d49	2026-08-12 21:33:02.965899+00	postgres
0047_add_dataset_module_tables.sql	71e17c06e3b9d2e4b4d7bcebcc4a43631f482bb8c9f0951e595067b4658e59e4	2026-08-12 21:33:02.993473+00	postgres
0048_path_addshiftdate.sql	cee20896ddfcdc042749ec4ae12e8bfc3a467a00963662ce0918585d1a26495b	2026-08-12 21:33:03.103913+00	postgres
0049_createSegLinkageTable.sql	61a413414b1d9ee0f0e1dfc8b052c4064c0bf64e64578155b67fc32266a1f5ae	2026-08-12 21:33:03.131146+00	postgres
0050_NewPM2026.sql	79fd740948b3a9aaa63f944368fa9efff5f85b8ed292771dcf5e0b44b1f5adf7	2026-08-12 21:33:03.159989+00	postgres
\.


--
-- Data for Name: version; Type: TABLE DATA; Schema: db_version; Owner: -
--

COPY db_version.version (version) FROM stdin;
49
\.


--
-- Data for Name: background_buttons; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.background_buttons (background_button_id, operation_name, object_class, button_text, tags) FROM stdin;
25	QuickCheckPublicPosdaConsistLike	Posda::ProcessPopup	Quick Public Posda Like Collection	{public_posda_consistency}
29	UpdateActivityTimepoint	Posda::ProcessPopup	Update Activity Timepoint	{activity_timepoints}
27	CreateActivityTimepointFromCollectionSite	Posda::ProcessPopup	Create Activity Timepoint	{activity_timepoints}
28	FixBadSopInstanceLungFusedCtPathology	Posda::ProcessPopup	Fix Bad SOP Instances in Lung-Fused-CT-Pathology	{"Curation of Lung-Fused-CT-Pathology"}
30	VisualReviewFromTimepoint	Posda::ProcessPopup	Schedule Visual Review	{activity_timepoints}
31	PhiReviewFromTimepoint	Posda::ProcessPopup	Schedule PHI Scan	{activity_timepoints}
32	ConsistencyFromTimePoint	Posda::ProcessPopup	Check Consistency	{activity_timepoints}
33	LinkRtFromTimepoint	Posda::ProcessPopup	Link RT Data for ItcTools	{activity_timepoints}
34	CheckStructLinkagesTp	Posda::ProcessPopup	Check Structure Set Linkages	{activity_timepoints}
35	DispositionNeededWorksheet	Posda::ProcessPopup	Make Worksheet for Diapositions Needed	{phi_maint}
36	PhiPublicScanTp	Posda::ProcessPopup	Public Phi Scan Based on Current TP by Activity	{activity_timepoints}
37	SummarizeStructLinkage	Posda::ProcessPopup	Summarize Structure Set Linkages for a File	{activity_timepoint_support}
38	BackgroundDciodvfyTp	Posda::ProcessPopup	Run Dciodvfy for Time Point	{activity_timepoints}
39	CondensedActivityTimepointReport	Posda::ProcessPopup	Produce Condensed Activity Timepoint Report	{activity_timepoints}
26	AnalyzeSeriesDuplicates	Posda::ProcessPopup	Analyze Series With Duplicates	{"ACRIN-FMISO-Brain Duplicate Elimination",dup_sops,activity_timepoint_support}
40	FilesInTpNotInPublic	Posda::ProcessPopup	Find Files in Tp, not in Public	{activity_timepoints}
41	CompareSopsInTpToPublic	Posda::ProcessPopup	Compare Corresponding SOPs in Time Point to Public	{activity_timepoints}
42	AnalyzeSeriesDuplicatesForTimepoint	Posda::ProcessPopup	Analyze Series In Time Point with Duplicates	{activity_timepoint_support}
43	CompareSopsTpPosdaPublic	Posda::ProcessPopup	Compare Sops in Timepoint, Posda, and Public	{activity_timepoint_support}
44	FixFilesWithNullNumberOfFrames	Posda::ProcessPopup	Fix Files With Null Number of Frames	{Exceptional-Responders_NCI_Oct2018_curation}
45	FixCtInExceptionalRespondersWithNullNumberOfFrames	Posda::ProcessPopup	Fix CT Files in Exceptional-Responders with Null Number of Frames	{Exceptional-Responders_NCI_Oct2018_curation}
46	PrivateTagReports	Posda::ProcessPopup	Create Private Tag Vr and Disposition Reports	{phi_maint}
47	BackgroundPrivateDispositionsTp	Posda::ProcessPopup	Apply Background Dispositions To Timepoint (non baseline date)	{activity_timepoints}
48	BackgroundPrivateDispositionsTpBaseline	Posda::ProcessPopup	Apply Background Dispositions To Timepoint (baseline date)	{activity_timepoints}
49	MakeWeeklyFilesReport	Posda::ProcessPopup	Generate Report of File Uploads By Type By Week	{downloads_by_date}
50	CompareSopsTpPosdaPublicLike	Posda::ProcessPopup	Compare Sops in Timepoint, Posda, and Public like Collection	{activity_timepoint_support}
1	ImportFromDicomFileEdit	Posda::ProcessPopup	Import Edits	{edit_files}
2	CheckPublicMissingFilesInSeriesByCollection	Posda::ProcessPopup	Check Missing Files Public	{bills_test}
3	CopyCollectionToStaging	Posda::ProcessPopup	Copy Files To Dir	{bills_test}
4	CheckStructLinkagesByCollectionSite	Posda::ProcessPopup	Check Struct Links	{struct_linkages}
5	CheckPosdaPublicConsistency	Posda::ProcessPopup	Check Public Posda	{public_posda_consistency}
6	BackOutEdit	Posda::ProcessPopup	Backout Import Edits	{edit_files}
7	QuickCheckPosdaPublicConsistency	Posda::ProcessPopup	Quick Check Posda PUblic	{public_posda_consistency}
8	SetUpPublicToPosdaCopy	Posda::ProcessPopup	Set Up Copy of Collection From Public To Posda	{public_posda_consistency}
9	StartPublicToPosdaCopy	Posda::ProcessPopup	Start a waiting Public to Posda Copy	{public_posda_consistency}
10	DciodvfyReport	Posda::ProcessPopup	Dciodvfy Report	{dciodvfy}
11	StartFixPublicToPosdaCopy	Posda::ProcessPopup	Retry failed Public Copy	{public_posda_consistency}
12	LookForDupSopsInPublicByCollectionSite	Posda::ProcessPopup	Look for Conflicting Sops already in Public By Collection, Site	{comparing_posda_to_public}
13	DeletePvtExceptCtp	Posda::ProcessPopup	Copy Collection to Scratch Deleting All Private tags exept CTP tags	{bills_test}
14	CheckRtReferenceChain	Posda::ProcessPopup	Check Rt Linkage Chain	{struct_linkages}
56	InitialAnonymizerCommandsTp	Posda::ProcessPopup	Produce Initial Anonymization File for Timepoint	{initial_anonymization,patient_mapping,activity_timepoints}
20	RejectEdits	Posda::ProcessPopup	Reject Edits	{find_patients,check_edits}
21	ImportEdits	Posda::ProcessPopup	Import Edits	{find_patients,check_edits}
22	CheckEditCurrent	Posda::ProcessPopup	Check If Edits Current	{find_patients,check_edits}
24	NonDicomPhiScan	Posda::ProcessPopup	Phi Scan of Non-Dicom Files	{non_dicom_phi}
18	ProcessVisualReview	Posda::ProcessPopup	Process Visual Review Results	{visual_review_new_workflow,visual_review_reports}
51	CompareSopsTpPosdaPublicCollectionLikeSiteEqual	Posda::ProcessPopup	Compare Sops in Timpoint, Posda, and Public like Collection for Site	{activity_timepoint_support}
52	AdHocReportForTracy	Posda::ProcessPopup	Make CPTAC Report	{clin_qual}
53	HideFilesVisbleInBadEquivalenceClassesByVisualReviewId	Posda::ProcessPopup	Hide Files in Equivalence Classes Marked Bad	{visual_review_status}
54	BackgroundLinkActivityToTemp	Posda::ProcessPopup	Link Files in Activity to Temp Directory	{send_series}
19	RepealEdits	Posda::ProcessPopup	Repeal Edits	{find_patients,check_edits,edit_status}
16	FirstPassPhiByCollection	Posda::ProcessPopup	First Pass Phi By Collection	{phi_status,simple_phi}
15	FirstPassPhiScanAndReport	Posda::ProcessPopup	First Pass Phi by collection, site and (optional) batch	{phi_status,simple_phi}
17	FullPhiById	Posda::ProcessPopup	Full Phi Report by Scan Id	{phi_status,simple_phi}
23	PhiPublicScan	Posda::ProcessPopup	Public Scan By Collection, Site	{phi_status,simple_phi}
55	CreateActivityTimepointFromImportName	Posda::ProcessPopup	Create Activity Timepoint From Import Description	{activity_timepoints}
\.


--
-- Data for Name: chained_query; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.chained_query (chained_query_id, from_query, to_query, caption) FROM stdin;
1	PixelTypes	FileIdByPixelType	files
2	HideEvents	HideEventInfo	Info
3	WhatHasComeInRecentlyWithSubject	ToExamineRecentFiles	files
4	CtSeriesWithCtImageInfoByCollection	CtImageDataConsistencyAcrossSeries	Image Data Consistent?
5	CtSeriesWithCtImageInfoByCollection	SeriesReport	rpt
6	QueriesRunning	GetQuery	drill
7	VisibleColSiteWithCtpLikeSite	DistinctSeriesByCollectionSite	Get Series
8	VisualReviewScanInstances	VisualReviewStatusById	Details
9	ListActivities	InboxContentByActivityId	Details
10	VisualReviewStatusById	VisualReviewStatusDetails	Details
11	ListOpenActivities	InboxContentByActivityId	Details
12	ListOpenActivities	CloseActivity	close
13	ListOpenActivitiesWithItems	InboxContentByActivityId	Details
14	ListOpenActivitiesWithItems	CloseActivity	close
15	ListClosedActivities	InboxContentByActivityId	Details
16	ListClosedActivitiesWithItems	ReOpenActivity	re-open
17	ListClosedActivitiesWithItems	InboxContentByActivityId	Details
18	ListClosedActivities	ReOpenActivity	re-open
19	ActivityStuffMoreWithEmailByUser	LinkEmailToActivity	file
20	ActivityStuffMoreWithEmailByUser	UnlinkEmailFromActivity	unfile
21	ActivityStuffMoreWithEmailByUserDateRange	LinkEmailToActivity	file
22	ActivityStuffMoreWithEmailByUserDateRange	UnlinkEmailFromActivity	unfile
\.


--
-- Data for Name: chained_query_cols_to_params; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.chained_query_cols_to_params (chained_query_id, from_column_name, to_parameter_name) FROM stdin;
1	samples_per_pixel	samples_per_pixel
1	bits_allocated	bits_allocated
1	bits_stored	bits_stored
1	high_bit	high_bit
1	pixel_representation	pixel_representation
1	planar_configuration	planar_configuration
1	photometric_interpretation	photometric_interpretation
2	when_done	day_of_change
2	reason_for	reason_for
2	user_name	user_name
3	subj	patient_id
3	time	import_time_1
3	time	import_time_2
4	series_instance_uid	series_instance_uid
5	series_instance_uid	series_instance_uid
6	pid	pid
7	collection	project_name
7	site	site_name
8	id	id
9	activity_id	activity_id
12	activity_id	activity_id
12	activity_id	activity_id
13	activity_id	activity_id
14	activity_id	activity_id
15	activity_id	activity_id
16	activity_id	activity_id
17	activity_id	activity_id
10	review_status	review_status
10	processing_status	processing_status
10	id	visual_review_instance_id
10	dicom_file_type	dicom_file_type
11	activity_id	activity_id
18	activity_id	activity_id
19	user_inbox_content_id	user_inbox_content_id
20	activity_id	activity_id
20	user_inbox_content_id	user_inbox_content_id
21	activity_id	activity_id
21	user_inbox_content_id	user_inbox_content_id
22	activity_id	activity_id
22	user_inbox_content_id	user_inbox_content_id
\.


--
-- Data for Name: popup_buttons; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.popup_buttons (popup_button_id, name, object_class, btn_col, is_full_table, btn_name) FROM stdin;
2	SopsDupsInDifferentSeriesByCollectionSite	Posda::PopupImageViewer	file_id	f	View
3	SopsDupsInDifferentSeriesByCollectionSite	Posda::PopupCompare	sop_instance_uid	f	Compare
1	%EditResults%	Posda::PopupCompareFilesPath	\N	f	Compare Files
4	DupSopsByCollectionSiteDateRange	Posda::PopupCompare	sop_instance_uid	f	Compare
5	DuplicateFilesBySop	Posda::PopupCompare	sop_instance_uid	f	Compare
6	DuplicateFilesBySop	Posda::PopupCompare	sop_instance_uid	f	Compare
7	DuplicateFilesBySop	Posda::PopupCompare	sop_instance_uid	f	Compare
9	GetSimilarDupContourCounts	Posda::PopupCompare	\N	t	Compare
10	DistinctSeriesByCollection	Posda::ProcessPopup	\N	t	BackgroundPhiScan
11	DistinctSeriesByCollection	Posda::ProcessPopup	\N	t	BackgroundDciodvfySeries
12	DistinctSeriesByCollection	Posda::ProcessPopup	\N	t	DciodvfySeriesReport
13	DistinctStudySeriesByCollection	Posda::ProcessPopup	\N	t	BackgroundApplyPrivateDispositions
14	GetDoses	Posda::ProcessPopup	\N	t	BackgroundDoseLinkageCheck
15	GetPlans	Posda::ProcessPopup	\N	t	BackgroundPlanLinkageCheck
16	GetSsByCollection	Posda::ProcessPopup	\N	t	BackgroundStructLinkageCheck
17	DistinctStudySeriesByCollectionSite	Posda::ProcessPopup	\N	t	BackgroundApplyPrivateDispositions
18	DistinctSeriesByCollectionSite	Posda::ProcessPopup	\N	t	BackgroundPhiScan
19	DistinctSeriesByCollectionSite	Posda::ProcessPopup	\N	t	BackgroundDciodvfySeries
20	DistinctSeriesByCollectionSite	Posda::ProcessPopup	\N	t	DciodvfySeriesReport
21	DistinctSeriesByCollectionSitePublic	Posda::ProcessPopup	\N	t	BackgroundPhiScan
22	%	Quince	series_instance_uid	f	view
8	%	choose	file_id	f	view
73	foo	Posda::TestPopup	id	\N	test
74	VisualReviewStatusById	Posda::TestRedirectPopup	id	\N	review
67	VisualReviewScanInstances	Posda::ProcessPopup	fubar	f	CreateActivityTimepoint
36	ColSiteDetails	Posda::ProcessPopup	\N	t	PhiScan
37	DistinctSeriesByPatient	Posda::ProcessPopup	\N	t	LinkSeries
38	DistinctSeriesByPatient	Posda::ProcessPopup	\N	t	PhiScan
39	DistinctSeriesByPatientAdvanced	Posda::ProcessPopup	\N	t	CheckConsistency
40	DistinctSeriesByPatientAdvanced	Posda::ProcessPopup	\N	t	DicomValidation
41	DistinctSeriesByPatientAdvanced	Posda::ProcessPopup	\N	t	LinkForDownload
42	DistinctSeriesByPatientAdvanced	Posda::ProcessPopup	\N	t	PrivateDispositions
43	PatientDetailsWithBlankCtp	Posda::ProcessPopup	\N	t	InitialAnonymizerCommands
44	PatientDetailsWithNoCtp	Posda::ProcessPopup	\N	t	InitialAnonymizerCommands
45	SummaryOfToFiles	Posda::ProcessPopup	\N	t	LinkSeries
46	SummaryOfToFilesForPatient	Posda::ProcessPopup	\N	t	LinkSeries
63	InboxContentByActivityId	DbIf::ShowSubprocessLines	sub_id	\N	view
47	GetZipUploadEventsByDateRangeNonDicomOnly	Posda::ProcessPopup	\N	t	ProcessRADCOMPUpload
49	GetXlsToConvert	Posda::ProcessPopup	\N	t	XlsConverter
50	GetXlsxToConvert	Posda::ProcessPopup	\N	t	XlsxConverter
48	GetDocxToConvert	Posda::ProcessPopup	\N	t	RadcompSubmissionConverter
51	GeFromToFilesFromNonDicomEditCompare	choose_to	to_file_id	f	view
52	GeFromToFilesFromNonDicomEditCompare	choose_from	from_file_id	f	view
53	AllPatientDetailsWithNoCtpLike	Posda::ProcessPopup	\N	t	InitialAnonymizerCommands
55	DistinctSeriesByCollectionSite	Posda::ProcessPopup	\N	t	VisualReview
56	SeriesWithDupSopsByCollectionSiteNew	Posda::ProcessPopup	\N	t	AnalyzeSeriesDuplicates
57	GetFilesWithNoSeriesInfoByCollection	Posda::ProcessPopup	\N	t	BackgroundProcessModules
58	InboxContentAll	Posda::ProcessPopup	\N	t	FileAndDismissNotifications
59	VisualReviewStatusById	Posda::ProcessPopup	\N	t	MakePassThru
61	VisualReviewStatusById	Posda::ProcessPopup	\N	t	ProcessVisualReview
62	VisualReviewStatusById	Posda::ProcessPopup	\N	t	SendBlankToDest
64	VisualReviewStatusDetails	Posda::ProcessPopup	\N	t	RetryFailedProjections
54	InboxContentByActivityId	choose_spreadsheet	spreadsheet_file_id	\N	view
60	VisualReviewStatusDetails	Posda::ProcessPopup	\N	t	HideEquivalenceClasses
65	VisualReviewStatusDetails	Posda::ProcessPopup	\N	t	ChangeReviewStatus
66	VisualReviewStatusById	Posda::ProcessPopup	\N	t	ApplyDispositions
68	DistinctVisibleSeriesByCollectionSite	Posda::ProcessPopup	\N	t	CreateActivityTimepointFromSeriesList
69	DistinctSeriesByPatientId	Posda::ProcessPopup	\N	t	CreateActivityTimepointFromSeriesList
70	ListSrPublic	DbIf::ShowSr	dicom_file_uri	\N	view
71	ListSrPosda	DbIf::ShowSr	file_path	\N	view
72	ListSrPosdaHidden	DbIf::ShowSr	file_path	\N	view
75	GetEditStatusByDisposition	DbIf::EditStatus	id	f	info
35	AllPatientDetailsWithNoCtp%	Posda::ProcessPopup	\N	t	InitialAnonymizerCommands
\.


--
-- Data for Name: query_tabs; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.query_tabs (query_tab_name, query_tab_description, defines_dropdown, sort_order, defines_search_engine) FROM stdin;
count_check	for checking counts	t	10	f
curation	queries used in curation	t	20	f
scripting	queries used in scripts	t	50	f
db_admin	queries used for db_maintenance	t	30	f
legacy	compatable with old interface	t	90	f
bills_test_queries	Bills testing ground	t	100	f
Consistency	Consistency Checks	t	50	f
DicomValidation	DICOM validation (dciodvfy)	t	40	f
Finalize	Finalize, download, etc	t	60	f
PHI	used for PHI scans etc	t	30	f
Phi	Phi scanning and review operations	t	30	f
UploadedData	Operations on uploaded data	t	10	f
VisualReview	Visual review related operations	t	20	f
initial_upload	used in initial uploads of tar files	t	10	f
Activities	Operartions related to reviewing Acivities	t	60	f
View Structured Reports	View Structured Reports	t	1	f
Status	Collects Status Related Filters	t	60	f
\.


--
-- Data for Name: query_tabs_query_tag_filter; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.query_tabs_query_tag_filter (query_tab_name, filter_name, sort_order) FROM stdin;
count_check	view_posda_backlog	1
count_check	downloads_by_date	2
count_check	counts_patient_status	3
curation	duplicate_sop_evaluation	1
curation	duplicate_sop_resolution	2
curation	linkage_check	3
curation	consistency_check	4
scripting	used_in	1
curation	phi_review	5
curation	dicom_batch_file_editing	6
curation	send_data_via_dicom	6
db_admin	db_stats	10
curation	visual_review_scheduling	7
scripting	for_popups	2
db_admin	db_config	20
curation	dciodvfy	8
bills_test_queries	under_development	1
legacy	.Unlimited	1
legacy	.Show No Tags	1
legacy	universal	3
bills_test_queries	old_queries	10
bills_test_queries	linkage	3
scripting	for_public_posda_compare	3
bills_test_queries	posda_db_populate	4
bills_test_queries	copy_from_public	5
bills_test_queries	comparing_public_to_posda	6
db_admin	postgres_stats	30
bills_test_queries	for_ct_evaluation	50
bills_test_queries	subprocess	60
bills_test_queries	non_dicom_editing	70
bills_test_queries	database_fixup	80
UploadedData	with_ctp_anonymization	10
UploadedData	without_ctp_anonymization	20
bills_test_queries	bills_ad_hoc_scripts	90
VisualReview	select_for_visual_review	20
VisualReview	visual_review_status	30
VisualReview	visual_review_reports	40
bills_test_queries	activities	100
bills_test_queries	activity_based	200
Activities	activities	1
bills_test_queries	trace_edits	300
Phi	PhiStatus	1
Activities	activity_timepoints	2
View Structured Reports	View Structured Reports	1
scripting	dicom_file_table	4
Activities	activity_based	3
Status	edit_status	10
Status	visual_review_status	5
Status	phi_status	7
\.


--
-- Data for Name: query_tag_filter; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.query_tag_filter (filter_name, tags_enabled) FROM stdin;
.Show No Tags	{}
.Unlimited	{}
for_popups	{universal,used_in_process_popup}
view_posda_backlog	{backlog_analysis_reporting_tools,backlog_round_history,backlog_status,universal}
review_roles	{universal,roles}
visual_review_tracking_processing	{visual_review_results,universal}
send_data_via_dicom	{universal,search_series,send_series,send_directory}
manage_posda_backlog	{universal,backlog_status,backlog}
db_config	{query_tags,query_tabs,popups}
counts_patient_status	{universal,count_queries,patient_status,adding_ctp}
dciodvfy	{dciodvfy,universal}
duplicate_sop_evaluation	{universal,dup_sops,sops_different_series,series_report}
dicom_batch_file_editing	{hash_unhashed,hide_files,apply_disposition,universal,edit_files,show_hidden}
monthly_report_queries	{universal,end_of_month}
for_ct_evaluation	{ct_image_consistency}
database_fixup	{dicom_file_type,reimport_queries}
linkage_check	{universal,plan_linkages,dose_linkages,struct_linkages,dose_linkages}
used_in	{universal,used_in_simple_phi,used_in_file_import_into_posda,used_in_import_edited_files,used_in_reconcile_tag_names,used_processing_structure_set_linkages,used_in_phi_maint,used_in_background_processing,used_in_dciodvfy,used_in_file_migration,used_in_linkage_check}
visual_review_scheduling	{universal,visual_review,visual_review_new_workflow}
for_public_posda_compare	{public_posda_counts}
linkage	{used_in_dose_linkage_check,used_in_plan_linkage_check,used_in_structure_linkage_check,old_linkage_checks,used_in_struct_linkage_check}
subprocess	{subprocess}
consistency_check	{series_consistency,study_consistency,universal,public_posda_consistency}
old_queries	{for_bill,for_bill_counts,for_bill_study_consistency,for_bill_series_consistency,old_visibility}
posda_db_populate	{posda_db_populate}
copy_from_public	{copy_from_public}
comparing_public_to_posda	{comparing_posda_to_public}
db_stats	{q_stats,q_stats_by_date,q_list,queries,query_tags,universal,schema}
phi_review	{universal,phi_schedule,simple_phi,phi_maint,meta_q_queries,scan_status}
duplicate_sop_resolution	{universal,dup_sops,hide_dup_sops,distinguished_digest}
phi_status	{phi_status}
select_for_phi	{select_for_phi}
series_for_phi	{series_selection}
phi_reports	{phi_reports}
find_patients	{find_patients,mapping_tables,for_scripting}
download_results	{patient_queries}
visual_review_status	{visual_review_status,visual_review_new_workflow}
trace_edits	{trace_edits}
non_dicom_editing	{non_dicom_edit,non_dicom_phi,non_dicom_phi_status,non_dicom_import,non_dicom_reject,radcomp}
bills_ad_hoc_scripts	{bills_ad_hoc_scripts}
select_for_visual_review	{visual_review_selection}
visual_review_reports	{visual_review_reports}
with_ctp_anonymization	{ctp_patients,ctp_col_site,ctp_details,check_edits,hide,check_dups}
PhiStatus	{scan_status}
activities	{activities,activity_support}
without_ctp_anonymization	{no_ctp_patients,no_ctp_details,patient_mapping,insert_pat_mapping,import_event}
View Structured Reports	{view_structured_reports}
under_development	{universal,hide_events,bills_test,for_tracy,radcomp,non_dicom_phi,non_dicom_phi_status,non_dicom_edit,testing_edit_objects}
dicom_file_table	{adding_pixels_to_dicom_file}
downloads_by_date	{downloads_by_date,import_events,universal}
edit_status	{edit_status}
activity_timepoints	{activity_timepoints,activity_timepoint_support,compare_series,clin_qual,manifests}
activity_based	{"ACRIN-FMISO-Brain Duplicate Elimination","Curation of Lung-Fused-CT-Pathology","CPTAC Bolus September 2018","ACRIN-NSCLC-FDG-PET Curation",Exceptional-Responders_NCI_Oct2018_curation,"Test Case based on Soft-tissue-Sarcoma",QIN-GBM-DSC-MRI-DRO/Barrow,"Reconcile Public and Posda for CPTAC"}
postgres_stats	{database_size,table_size,postgres_query_stats,invoking_user}
\.


--
-- Data for Name: role; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.role (role_name) FROM stdin;
legacy_bbennett
legacy_ksmith01
legacy_priorf
legacy_rddobbins
legacy_smberryman
legacy_tracyn
workflow_1
curator
developer
SrViewer
\.


--
-- Data for Name: role_tabs; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.role_tabs (role_name, query_tab_name, sort_order) FROM stdin;
legacy_bbennett	UploadedData	10
legacy_bbennett	bills_test_queries	20
legacy_bbennett	count_check	30
legacy_bbennett	curation	40
legacy_bbennett	db_admin	50
legacy_bbennett	legacy	60
legacy_bbennett	scripting	70
legacy_ksmith01	bills_test_queries	10
legacy_ksmith01	count_check	20
legacy_ksmith01	curation	30
legacy_ksmith01	db_admin	40
legacy_ksmith01	legacy	50
legacy_ksmith01	scripting	60
legacy_priorf	count_check	10
legacy_priorf	curation	20
legacy_priorf	legacy	30
legacy_priorf	scripting	40
legacy_rddobbins	count_check	10
legacy_rddobbins	curation	20
legacy_rddobbins	db_admin	30
legacy_rddobbins	legacy	40
legacy_rddobbins	scripting	50
legacy_smberryman	curation	10
legacy_smberryman	legacy	20
legacy_tracyn	bills_test_queries	10
legacy_tracyn	count_check	20
legacy_tracyn	curation	30
legacy_tracyn	legacy	40
legacy_tracyn	scripting	50
curator	UploadedData	10
curator	VisualReview	20
curator	Phi	30
developer	bills_test_queries	20
developer	count_check	30
developer	curation	40
developer	db_admin	50
developer	legacy	60
developer	scripting	70
curator	Activities	40
SrViewer	View Structured Reports	1
curator	Status	30
\.


--
-- Data for Name: spreadsheet_operation; Type: TABLE DATA; Schema: dbif_config; Owner: -
--

COPY dbif_config.spreadsheet_operation (operation_name, command_line, operation_type, input_line_format, tags, can_chain, outdated, worker_priority) FROM stdin;
AnnotateTimeline	InsertListOfAnnotatedFiles.pl <?bkgrnd_id?> "<comment>" <notify>	background_process	<file_id>&<file_name>&<mime_type>&<description>	{activity_timepoints,send_series_via_dicom,bills_test}	\N	f	0
BackgroundEditTpQ	BackgroundEditorTpQ.pl <?bkgrnd_id?> <activity_id> "<edit_description>" <notify>	background_process	<series_instance_uid>&<op>&<tag>&<val1>&<val2>	{activity_timepoints}	\N	f	1
BuildEditTimepointTp	BuildEditTimepointTp.pl <?bkgrnd_id?> <activity_id> <subprocess_invoc_id> <notify>	background_process	\N	{edit_files}	\N	f	1
EditReportsTp	EditReportsTp.pl <?bkgrnd_id?> <activity_id> <subprocess_invoc_id> <notify>	background_process	\N	{edit_files}	\N	f	1
FindWhichSubprocessesCreatedTimepointByUser	FindWhichSubprocessesCreatedTimepointByUser.pl <?bkgrnd_id?> <activity_id> <user> <notify>	background_process	\N	{temp}	\N	f	0
ConsolidateTimepoints	ConsolidateActivityTimepoints.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<activity_timepoint_id>	{activity_timepoints}	\N	f	0
SRPhiScanOp	SRPhiScan.pl <?bkgrnd_id?> <activity_id> <notify>	background_process		{"PHI report"}	\N	f	0
AddFilesToTimepoint	AddFilesToTimepoint.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<file_id>	{activity}	\N	f	0
CompareDupSopsInTimepoint	CompareDupSopsInTp.pl <?bkgrnd_id?> <activity_id> <activity_timepoint_id> <notify>	background_subprocess		{dup_sops}	\N	f	0
ListOfFilesBySeriesAndTimepoint	ListOfFilesBySeriesAndTimepoint.pl <?bkgrnd_id?> <activity_id> <activity_timepoint_id> <notify>	background_process	<series_instance_uid>	{Duke,DBT}	\N	f	0
SelectGoodAndBadFilesFromDupSopsWorksheet	SelectGoodAndBadFilesFromDupSopsWorksheet.pl <?bkgrnd_id?> <activity_id> <comparison_id> <notify>	background_process	<equiv_class>&<select>	{dup_sops}	\N	f	0
ApplyMasks	ApplyMasks.py <?bkgrnd_id?> <activity_id> <visual_review_instance_id> <notify>	background_process		{export}	\N	f	0
ImportDownloadableDirectory	ImportDownloadableDirectory.pl <?bkgrnd_id?> <activity_id> "<comment>" "<sub_dir>" <notify>	background_process		{VA,dispositions}	\N	f	0
MakeUIDMap	create-hashed-uid-mapping.py <?bkgrnd_id?> <notify> <timepoint_id>	background_process		{}	\N	f	0
BackgroundEditTp	BackgroundEditorTp.pl <?bkgrnd_id?> <activity_id> "<edit_description>" <notify>	background_process	<series_instance_uid>&<op>&<tag>&<val1>&<val2>	{activity_timepoints}	\N	f	1
BackgroundPrivateDispositionsTpBaseline	BackgroundPrivateDispositionsTpBaseline.pl <?bkgrnd_id?> <activity_id>  "<notify>" "<skip_dispositions>" "<upd_nbia>" "<dir>"	background_process		{activity_timepoints}	\N	f	1
SR_phiscanOp	SR_phiscan.pl <?bkgrnd_id?> <activity_id> <notify>	background_process		{"PHI report"}	\N	f	0
MakeDownloadableNonDicomTp	MakeDownloadableNonDicomTp.pl <?bkgrnd_id?> <activity_id> <sub_dir> <notify>	background_process		{send_series}	\N	f	0
PopulateNiftiSlicesAndProjectionsForTimepoint	PopulateNiftiSlicesAndProjectionsForTimepoint.pl <?bkgrnd_id?> <activity_id> <notify> <render_slices> <render_volumes> <render_projections> <verbose>	background_process		{nifti}	\N	f	1
Path_SVS_VisualReview	PathologyScheduleSVSReview.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{visual_review}	\N	f	0
CollectUidsFromFileList	CollectAllUidsFromFileList.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<file_id>	{activity_timepoint}	\N	f	1
BackgroundSwapDicomPixelsData	BackgroundByteSwapDicomFilesInTimepoint.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{byte_swapping}	\N	f	0
BackgroundFixRtstructTp	BackgroundFixStructLinkagesTp.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<img_series>&<struct_file_id>	{activity_timepoints}	\N	f	0
NiftiScheduleVisualReview	NiftiScheduleVisualReview.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{visual_review}	\N	f	0
PopulateFileNiftiTp	PopulateFileNiftiTp.py <?bkgrnd_id?> <activity_id> <update_existing> <notify>	background_subprocess		{nifti}	\N	f	1
PhiVaPublicScanDD	PhiVaPublicScanDD.pl <?bkgrnd_id?> <activity_id> <rel_dir> <max_rows> <notify>	background_process		{simple_phi,va}	\N	f	1
SRProposeEditsTp	SRProposeEditsTp.pl <?bkgrnd_id?> <activity_id> <scan_id> <notify> "<sep_char>"	background_process	<element><sep_char><q_value><sep_char><path_sig_pattern><sep_char><p_op><sep_char><q_arg1><sep_char><q_arg2>	{simple_phi,activity_timepoints}	\N	f	0
CopyPriorTimepoint	CopyPriorTimepoint.py <?bkgrnd_id?> <activity_id> <old_tp_id> <notify>	background_process		{backup}	\N	f	1
Path_Commit_Edits	PathologyCommitEdits.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<activity_id>	{pathology,edits}	\N	f	0
NiftiPhiScan	NiftiPhiScan.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{phi_reports}	\N	f	0
BackgroundPopulateSegStructFile	BackgroundPopulateSegStructFiles.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<file_id>	{SegBitmaps}	\N	f	1
BackgroundDciodvfyTp	BackgroundDciodvfyTp.pl <?bkgrnd_id?> <activity_id> <type> <notify>	background_process		{activity_timepoint}	\N	f	1
UncompressFilesTp	UncompressFilesTp.py <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{uncompress,activity_timepoint}	\N	f	0
NewFirstPassPhi	NewFirstPassPhiScan.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<series_instance_uid>	{bills_test,new_workflow}	\N	f	0
FileAndDismissNotifications	FileAndDismissNotification.pl <?bkgrnd_id?> <activity_id> "<description>" <notify>	background_process	<id>	{activity_support}	\N	f	0
PhiReviewFromTimepoint	SchedulePhiReviewFromActivityTimepoint.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{visual_review}	\N	f	1
DispositionNeededWorksheet	DispositionsNeededWorksheet.pl <?bkgrnd_id?> <notify>	background_process	\N	{phi_maint}	\N	f	1
BackgroundPrivateDispositionsTp	BackgroundPrivateDispositionsTp.pl <?bkgrnd_id?> <activity_id> "<uid_root>" "<offset>" "<notify>" "<skip_dispositions>" "<upd_nbia>" "<dir>" "<override_site_name>"	background_process		{activity_timepoints}	\N	f	1
VisualReviewFromTimepoint	ScheduleVisualReviewFromActivityTimepoint.pl <?bkgrnd_id?> <activity_id> <notify> "<skip_rendering>"	background_process		{visual_review}	\N	f	0
AnalyzeSeriesDuplicatesForTimepoint	AnalyzeTpSeriesDuplicates.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{activity_timepoint_support}	\N	f	0
BackgroundUpdatePrivateDisposition	BackgroundUpdatePrivateDispositions.pl <?bkgrnd_id?> "<why>" <notify>	background_process	<id>&<disp>	{phi_maint}	\N	f	0
RejectEditsTp	RejectEditsTp.pl <?bkgrnd_id?> <activity_id> <subprocess_invoc_id> <notify>	background_process	\N	{find_patients}	\N	f	0
PhiPublicScanTp	PhiPublicScanTp.pl <?bkgrnd_id?> <activity_id> <max_rows> <notify>	background_process	\N	{simple_phi}	\N	f	1
BackgroundFixRtstruct	BackgroundFixStructLinkages.pl <?bkgrnd_id?> "<comment>" <notify>	background_process	<img_series>&<struct_file_id>	{activity_timepoints}	\N	t	0
PhiPublicScan	PhiPublicScan.pl <?bkgrnd_id?> <activity_id> <max_rows> "<collection>" "<site>" <notify>	background_process		{simple_phi}	\N	t	0
CountFilesInSeries	TotalFilesForSelectedSeries.pl <?bkgrnd_id?> <notify>	background_process	<series_instance_uid>	{bills_test}	\N	t	0
CheckCollectionAgainstPatientId	CheckCollectionAgainstPatientId.pl <?bkgrnd_id?> <notify>	background_process	<collection>&<patient_id>	{bills_test}	\N	t	0
RejectEdits	RejectEdits.pl <?bkgrnd_id?> <subprocess_invoc_id> <notify>	background_process	\N	{find_patients}	\N	t	0
MakeDownloadableDirectoryTp	MakeDownloadableDirectoryTp.pl <?bkgrnd_id?> <activity_id> <sub_dir> <notify>	background_process		{send_series}	\N	f	0
CreateDownloadableDirectoryAllTp	CreateDownloadableDirectoryAllTp.pl <?bkgrnd_id?> <activity_id> <sub_dir> <notify>	background_process		{test}	\N	f	0
ProposeEditsTp	ProposeEditsTp.pl <?bkgrnd_id?> <activity_id> <scan_id> <notify> "<sep_char>"	background_process	<element><sep_char><vr><sep_char><q_value><sep_char><num_series><sep_char><p_op><sep_char><q_arg1><sep_char><q_arg2>	{simple_phi,activity_timepoints}	\N	f	0
ImportEdits	ImportEdits.pl <?bkgrnd_id?> <subprocess_invoc_id> <notify>	background_process	\N	{find_patients}	\N	t	0
PhiScan	NewPhiScan.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<series_instance_uid>	{scan_status,phi_status,new_phi}	\N	t	0
BackgroundEdit	BackgroundEditor.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<series_instance_uid><op><tag><val1><val2>	{activity_timepoints,uses_field_separator}	\N	t	0
CreateActivityTimepointFromImportEventId	CreateActivityTimepointFromImportEventIdAll.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<import_event_id>	{activity_timepoints}	\N	f	0
SimplePhiScan	PhiSimpleScan.pl "<description>" <file_query_name> <notify>	legacy	<series_instance_uid>	{simple_phi}	\N	f	0
MakeWeeklyFilesReport	MakeWeeklyLoadReport.pl <?bkgrnd_id?> <notify> <from> <to>	background_process	\N	{downloads_by_date}	\N	f	1
CreateActivityTimepointFromSeriesList	CreateActivityTimepointFromSeriesList.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<series_instance_uid>	{activity_timepoints}	\N	t	0
RetryFailedProjections	RetryFailedProjections.pl <?bkgrnd_id?> <notify>	background_process	<image_equivalence_class_id>&<processing_status>&<review_status>	{visual_review_status}	\N	f	0
DeleteSeriesFromActivityTimepoint	DeleteSeriesFromActivityTimepoint.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<series_instance_uid>	{activity_timepoints}	\N	f	0
AddSeriesToActivityTimepoint	AddSeriesToActivityTimepoint.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<series_instance_uid>	{activity_timepoint_support}	\N	f	0
CompareSopsInTpToPublic	CompareSopsInTpToPublic.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{activity_timepoints_support}	\N	f	0
LinkRtFromTimepoint	LinkRtByActivityTimepoint.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{timepoint_buttons}	\N	f	0
CondensedActivityTimepointReport	CondensedActivityTimepointReport.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{timepoint_buttons}	\N	f	0
ConsistencyFromTimePoint	AnalyzeStudySeriesConsistencyByActivity.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{timepoint_buttons}	\N	f	1
FilesInTpNotInPublic	FilesInLatestActivityNotInPublic.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{activity_timepoints_support}	\N	f	0
ImportPatientMapping	ImportPatientMapping.pl <?bkgrnd_id?> <notify>	background_process	<from_patient_id>&<to_patient_id>&<to_patient_name>&<collection_name>&<site_name>&<batch_number>&<date_shift>&<diagnosis_date>&<baseline_date>&<uid_root>	{bills_test,mapping_tables,patient_mapping}	\N	f	0
PrivateTagReports	PrivateElementReports.pl <?bkgrnd_id?> <notify>	background_process	\N	{phi_maint}	\N	f	0
CreateActivityTimepointFromPatientList	CreateActivityTimepointFromPatientList.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<collection>&<site>&<patient_id>	{activity_timepoints}	\N	f	0
InitialAnonymizerCommandsTp	ProduceInitialAnonymizerCommandsTp.pl <?bkgrnd_id?> <collection> <site> <activity_id> <notify>	background_process	\N	{initial_anonymization,patient_mapping}	\N	f	0
CompareTimepoints	CompareTimepoints.pl <?bkgrnd_id?> <activity_id> <from_timepoint_id> <to_timepoint_id> <notify>	background_process		{}	\N	f	0
CreateActivityTimepointFromImportId	CreateActivityTimepointFromImportEventId.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<import_event_id>	{activity_timepoints}	\N	f	0
CopyPriorTimepointInSeriesOnly	CopyPriorTimepointInSeriesOnly.pl <?bkgrnd_id?> <activity_id> <old_tp_id> <notify>	background_subprocess	<series_instance_uid>	{activity_timepoints}	\N	f	0
CopyPriorTimepointExcludingFiles	CopyPriorTimepointExcludingFiles.py <?bkgrnd_id?> <activity_id> <old_tp_id> <notify>	background_process	<file_id>	{activity_timepoints}	\N	f	0
ConsolidateActivities	ConsolidateActivities.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<activity_id>	{activity_timepoints}	\N	f	0
CreateActivityTimepointFromFileIds	CreateActivityTimepointFromFileIds.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<file_id>	{activity_timepoints}	\N	f	0
CheckStructLinkagesTp	CheckStructLinkagesTpId.pl <?bkgrnd_id?> <activity_id> "<check_public>" <notify>	background_process		{timepoint_buttons}	\N	f	0
CreateCompleteActivityTimepointFromImportEvent_id	CreateCompleteActivityTimepointFromImportEventId.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<import_event_id>	{activity_timepoints}	\N	f	0
RemoveFilesMarkedBadFromActivity	RemoveFilesMarkedBadFromActivity.pl <?bkgrnd_id?> <activity_id> <visual_review_id> <notify>	background_process		{visual_review}	\N	f	0
InsertPrivateTagKb	InsertPrivateTagKb.pl <?bkgrnd_id?> <activity_id> <is_dry_run> <notify>	background_process	<pt_signature>&<pt_consensus_vr>&<pt_consensus_name>&<pt_consensus_vm>&<pt_consensus_description>&<pt_consensus_disposition>	{}	\N	f	0
FindCorrespondingPosdaPublicPath	CorrespondingFilesPosdaPublic.pl <?bkgrnd_id?> <notify>	background_process	<file_id>	{public_posda_compare}	\N	f	0
CreateActivityTimepointFromFileList	CreateActivityTimepointFromFileList.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<file_id>	{activity_timepoints}	\N	f	0
ImportEditsTp	ImportEditsTp.pl <?bkgrnd_id?> <activity_id> <subprocess_invoc_id> <notify>	background_process	\N	{edit_files}	\N	f	1
Path_PHI_Scan	PathologyPhiScan.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{phi_reports}	\N	f	0
ConvertBigEndianToLittle	ConvertBigEndianToLittle.py <?bkgrnd_id?> "<activity_id>" "<notify>"	background_process		{visual_review}	\N	f	0
BackgroundEditBySopInstanceTp	BackgroundEditBySopInstanceTp.pl <?bkgrnd_id?> <activity_id> <desciption> <notify>	background_process	<unmapped_uid><mapped_uid><sop_instance_uid><operation><tag><val1><val2>	{editor}	\N	t	0
ConstructCrosswalk	CrosswalkConstructor.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<batch_1_uids><batch_2_uids><batch_3_uids><batch_4_uids><batch_5_uids>	{editor}	\N	t	0
MakeIopIppReportForSeriesInTimepoint	MakeIopIppReportForSeriesInTimepoint.pl <?bkgrnd_id?> <activity_id> <activity_timepoint_id> <series_instance_uid> <notify>	background_process	\N	{structure}	\N	f	0
CreateImportEventFromSeriesInPublic	CreateImportEventFromSeriesInPublic.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<series_instance_uid>	{copy_from_public}	\N	t	0
MakeDukeDbtMappingSpreadsheet	MakeDukeDbtMappingSpreadsheet.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{Duke,DBT}	\N	t	0
SlowRoll0	SlowRoll.pl <?bkgrnd_id?> <activity_id> <notify>	background_process		{demo_background}	\N	t	0
CompareDuplicateSops	CompareDupSopList.pl	legacy	<sop_instance_uid>	{dup_sops}	\N	t	0
AssociateNiftisWithDicoms	AssociateNiftisWithDicoms.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<activity_timepoint_id>&<nifti_file_id>&<series_instance_uid>	{nifti}	\N	t	0
ScanPhi	PhiScan.pl <type> "<description>"	legacy	<series_instance_uid>, <signature>	{phi_review}	\N	t	0
LinkDirectory	MakeLinkedDirectory.pl <target_dir>	legacy	<path>, <sop_instance_uid>	{send_series}	\N	t	0
AddInitialStatus	PopulatePatStat.pl	legacy	<patient_id>, <status>	{patient_status}	\N	t	0
ChangePatientStatus	UpdatePatStat.pl <who> "<why>"	legacy	<patient_id>, <old_status>, <new_status>	{patient_status}	\N	t	0
ExtractZ	ExtractZ.pl	legacy	<file_id>&<unique_pixel_data_id>&<ipp>	{}	\N	t	0
PseudoNominizerEditsConstructor	PseudoNominizerEditsConstructor.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<operation_scope>&<operation>&<tag>&<value1>&<value2>&<patient_id>&<study_instance_uid>&<series_instance_uid>&<sop_instance_uid>&<unmapped_uid>&<mapped_uid>	{pseudonominizer}	\N	t	0
PhiVaPublicScanTp	PhiVaPublicScanTp.pl <?bkgrnd_id?> <activity_id> <import_event_id> <max_rows> <notify>	background_process		{simple_phi,va}	\N	t	0
SlowRoll1	SlowRoll.pl <?bkgrnd_id?> <activity_id> <notify>	background_process		{demo_background}	\N	t	1
ProcessSeriesWithHeads	ProcessSeriesWithHeads.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<series_instance_uid>&<has_head>	{defacing}	\N	t	0
MakePatHierachy	GetHierarchyFromSeries.pl <?bkgrnd_id?> <notify>	background_process	<series_instance_uid>	{bills_test}	\N	t	0
UnHideFilesWithStatus	UnHideFilesWithStatus.pl <who> "<why>"	legacy	<file_id>&<old_visibility>	{hide_files,hide_dup_sops}	\N	t	0
SplitPdxPilot	GeneratePdxEdits.pl <?bkgrnd_id?> <rel_dest_root> <notify>	background_process	<patient_id>&<new_patient_id>&<new_study_desc>&<new_series_desc>	{bills_test}	\N	t	0
BackgroundDoseLinkageCheck	BackgroundDoseLinkageCheck.pl <?bkgrnd_id?> <notify_email>	background_process	<file_id>&<collection>&<site>&<patient_id>&<series_instance_uid>	{background}	\N	t	0
DciodvfySeriesReport	BackgroundDciodvfySeriesReport.pl <?bkgrnd_id?> "<description>" <scan_id> /cache/UserData/DbIf/PreparedReports/<report_file_name> <notify>	background_process	<series_instance_uid>	{dciodvfy}	\N	t	0
CopyBySeriesToScratch	CopyBySeriesToScratch.pl <to_dir> <notify>	legacy	<patient_id>&<study_instance_uid>&<series_instance_uid>	{send_series,apply_disposition}	\N	t	0
BackgroundPlanLinkageCheck	BackgroundPlanLinkageCheck.pl <?bkgrnd_id?> <notify_email>	background_process	<file_id>&<collection>&<site>&<patient_id>&<series_instance_uid>	{background}	\N	t	0
CompareSpreadsheetToPosda	compare_spreadsheet_to_posda.py <?bkgrnd_id?> "<collection>" "<site>" "<notify>"	background_process	<filename>,<collection>,<site>,<patient>,<series>,<sop>,<md5sum>,<size>	{background}	\N	t	0
SendPublicSeriesToDestination	SendPublicSetOfSeriesToDestination.pl <host> <port> <called> <calling>	legacy	<series_instance_uid>	{send_series}	\N	t	0
CreateActivityListFromPatientCountAndUploadSpecSpreadsheet	CreateActivityListFromPatientCountAndUploadSpecSpreadsheet.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<patient_id>&<num_files>&<import_comment_like>&<import_type_like>&<from>&<to>	{activity_timepoints}	\N	t	0
FixCtpFileRow	FixCtpFileRow.pl <?bkgrnd_id?> <notify>	background_process	<file_id>&<file_path>	{bills_test}	\N	t	0
SetUpPublicToPosdaCopy	SetUpPublicToPosdaCopy.pl <?bkgrnd_id?> <collection> <notify> "<why_done>"	background_process	\N	{pubic_posda_consistency}	\N	t	0
StartPublicToPosdaCopy	BackgroundPublicToPosdaCopy.pl <?bkgrnd_id?> <copy_id> "<why>" <notify>	background_process	\N	{pubic_posda_consistency}	\N	t	0
UnHideSeriesWithStatus	UnhideBatchSeriesWithStatus.pl <who> "<why>"	legacy	<series_instance_uid>	{hide_files}	\N	t	0
StartFixPublicToPosdaCopy	BackgroundFixPublicToPosdaCopy.pl <?bkgrnd_id?> <copy_id> "<why>", <notify>	background_process	\N	{public_posda_consistency}	\N	t	0
LookForDupSopsInPublicByCollectionSite	LookForPublicDupSops.pl <?bkgrnd_id?> "<collection>" "<site>" <notify>	background_process	\N	{comparing_posda_to_public}	\N	t	0
BuildUidMap	BuildUidMap.pl <?bkgrnd_id?> <notify>	background_process	<unmapped_uid>	{bills_test}	\N	t	0
DeletePvtExceptCtp	DeletePrivateFromCollection.pl <?bkgrnd_id?> <collection> /nas/public/posda/scratch/converted/<rel_to_dir> <notify>	background_process	\N	{bills_test}	\N	t	0
HidePatientWithStatus	HideBatchPatientWithStatus.pl <who> "<why>"	legacy	<patient_id>	{hide_files,hide_dup_sops}	\N	t	0
MakeRtReport	MakeRtReport.pl <?bkgrnd_id?> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>&<modality>&<num_files>	{bills_test}	\N	t	0
CheckRtReferenceChain	CheckRtReferenceChain.pl <?bkgrnd_id?> <collection> <site> <notify>	background_process	\N	{struct_linkages}	\N	t	0
AdHocReportForTracy	MakeCptacReport.pl <?bkgrnd_id?> <notify>	background_process	\N	{clin_qual}	\N	t	0
LinkSeries	BackgroundLinkSeries.pl <?bkgrnd_id?> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>	{patient_queries}	\N	t	0
InsertPatientMapping	ProcessCollectionSiteWorksheet.pl <?bkgrnd_id?>	background_process	<site_code>&<collection_code>&<site_id>&<site_name>&<collection_name>	{bills_test,mapping_tables,patient_mapping}	\N	t	0
ProcessRADCOMPUpload	CategorizeRadcompFiles.pl <?bkgrnd_id?> <collection> <site> <notify>	background_process	<import_event_id>	{radcomp}	\N	t	0
RadcompSubmissionConverter	RadcompSubmissionConverter.pl <?bkgrnd_id?> <notify>	background_process	<file_id>	{radcomp}	\N	t	0
XlsConverter	XlsConverter.pl <?bkgrnd_id?> <notify>	background_process	<file_id>	{radcomp}	\N	t	0
FullPhiById	FullPhiById.pl <?bkgrnd_id?> <scan_id> <notify> <max_rows>	background_process		{bills_test}	\N	t	0
CompareFileList	CompareFileList.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<from_file_id>&<to_file_path>	{file_compare}	\N	t	0
InitializeFileNiftiDefacing	InitializeFileNiftiDefacing.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<nifti_file_id>	{nifti}	\N	t	0
XlsxConverter	XlsxConverter.pl <?bkgrnd_id?> <notify>	background_process	<file_id>	{radcomp}	\N	t	0
NonDicomPhiScan	NonDicomPhiScan.pl <?bkgrnd_id?> <collection> <site> <notify>	background_process	\N	{non_dicom_phi}	\N	t	0
ProposeCsvEdits	ProposeCsvEdits.pl <?bkgrnd_id?> <scan_id> "<description>" <notify>	background_process	<type>&<path>&<q_value>&<num_files>&<p_op>&<q_arg1>&<q_arg2>&<q_arg3>	{non_dicom_edit}	\N	t	0
ProposeJsonEdits	ProposeJsonEdits.pl <?bkgrnd_id?> <scan_id> "<description>" <notify>	background_process	<type>&<path>&<q_value>&<num_files>&<p_op>&<q_arg1>&<q_arg2>&<q_arg3>	{non_dicom_edit}	\N	t	0
BackgroundCsvEdit	BackgroundCsvEditor.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<file_id>&<op>&<path>&<val1>&<val2>&<val3>	{edit,non_dicom_edit}	\N	t	0
BackgroundJsonEdit	BackgroundJsonEditor.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<file_id>&<op>&<path>&<val1>&<val2>&<val3>	{edit,non_dicom_edit}	\N	t	0
ImportNonDicomEdits	ImportNonDicomEditedFiles.pl <?bkgrnd_id?> <subprocess_invoc_id> <notify>	background_process	\N	{non_dicom_edit}	\N	t	0
GenerateYearOfDiagnosisEdits	GenerateEditsForYearsOfDiagnosis.pl <?bkgrnd_id?> <notify>	background_process	<patient_id>&<year>	{bills_ad_hoc_scripts}	\N	t	0
RadcompPrivateDisp	BackgroundPrivateDispositionsByPatShift.pl <?bkgrnd_id?> <to_dir> <uid_root> <notify>	background_process	<patient_id>&<study_uid>&<series_uid>&<offset>	{bills_test}	\N	t	0
QuickCheckPublicPosdaConsistLike	QuickPublicPosdaCompareLikeCollection.pl <?bkgrnd_id?> "<collection_pat>"  <notify>	background_process	\N	{public_posda_consistency}	\N	t	0
ProposeAdHocMelanomaEdits	ProposeAdHocMelanomaEdits.pl <?bkgrnd_id?> <shift> <old_uid_root> <new_uid_root> <notify>	background_process	<patient_id>&<series_uid>&<study_date>&<num_files>&<pat_id_for_diag_date>&<diag_date>	{bills_test,bills_ad_hoc_scripts}	\N	t	0
BackgroundConvertDefacedNiftisToDicom	BackgroundConvertDefacedNiftisToDicom.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<nifti_file_id>	{nifti}	\N	t	0
BackgroundHideEarlyDupSops	BackgroundHideEarlyDupSopsInSeries.pl <?bkgrnd_id?> <notify> "<reason>"	background_process	<series_instance_uid>	{activity_timepoint_support}	\N	t	0
CompareSopsTpPosdaPublic	CompareSopsTpPosdaPublic.pl <?bkgrnd_id?> "<collection>" <activity_id> <notify>	background_process	\N	{activity_timepoint_support}	\N	t	0
BackgroundUpdatePrivateDispositionEle	BackgroundUpdatePrivateDispositionsEle.pl <?bkgrnd_id?> "<why>" <notify>	background_process	<element_sig_pattern>&<disp>	{phi_maint}	\N	t	0
BackgroundHideSeriesByCollection	BackgroundHideSeriesByCollection.pl <?bkgrnd_id?> "<reason>" <collection> <notify>	background_process	<series_instance_uid>	{activity_timepoint_support}	\N	t	0
BackgroundConvertSeriesInTpToNifti	BackgroundConvertSeriesInTpToNifti.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<series_instance_uid>	{nifti}	\N	t	0
BackgroundDciodvfySeries	BackgroundDciodvfySeries.pl <?bkgrnd_id?> "<description>" <type> <notify>	background_process	<series_instance_uid>	{dciodvfy}	\N	t	0
BackgroundPhiScan	PhiBackgroundScan.pl <?bkgrnd_id?> "<description>" <file_query_name> <notify>	background_process	<series_instance_uid>	{background,simple_phi}	\N	t	0
TestProcessEditByStudy	TestProcessBackgroundEditStudyInstructions.pl <?bkgrnd_id?> <notify>	background_process	<study_instance_uid>&<op>&<tag>&<val1><val2>	{testing_edit_objects}	\N	t	0
PopulateFileImport	PopulateFileImportForImportEvent.pl <?bkgrnd_id?> <import_event_id> <notify>	background_process	<file_name>&<digest>	{QIN-GBM-DSC-MRI-DRO/Barrow}	\N	t	0
SimpleBackgroundTestProcess	SimpleBackgroundTestSubprocess.pl <?bkgrnd_id?> "<message>" <notify>	background_process	<column1>&<column2>&<column3>	{bills_test}	\N	t	0
CopySeriesFromPublic	CopySeriesFromPublic.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<series_instance_uid>	{nbia_copy}	\N	t	0
HelloWorldPerl	BackgroundHelloWorldWithInput.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<series_instance_uid>	{foo}	\N	t	0
BackgroundCompareFromTo	BackgroundCompareFromToFiles.pl <?bkgrnd_id?> <notify>	background_process	<sop_instance_uid>&<from_file>&<to_file>	{dup_sops,edit_files}	\N	t	0
MakeEditProposal	MakeEditProposal.pl <?bkgrnd_id?> <scan_id> <notify>	background_process	<element>&<vr>&<value>&<description>	{simple_phi}	\N	t	0
CheckCounts1	CompareCounts1.pl <?bkgrnd_id?> "<collection>" <uid_root> "<site>" "<notify>"	background_process	<id>&<study_instance_uid>&<series_instance_uid>&<num_files>	{bills_test}	\N	t	0
CompareSpreadsheetToIntake	compare_spreadsheet_to_intake.py <?bkgrnd_id?> "<collection>" "<site>" "<notify>"	background_process	<filename>,<collection>,<site>,<patient>,<series>,<sop>,<md5sum>,<size>	{background}	\N	t	0
BackgroundApplyPrivateDispositions	BackgroundApplyPrivateDispositions.pl <?bkgrnd_id?> <to_dir> <uid_root> <offset> <notify>	background_process	<patient_id>&<study_uid>&<series_uid>	{edit,send_series}	\N	t	0
ImportFromDicomFileEdit	ImportEditedFilesFromDicomEditCompare.pl <?bkgrnd_id?> <sub_invoc_id> <files_per_round> <max_queue_size> <notify>	background_process	\N	{edit_files}	\N	t	0
CheckStructLinkagesByCollectionSite	CheckStructLinkages.pl <?bkgrnd_id?> <collection> <site> <notify>	background_process	\N	{struct_linkages}	\N	t	0
BackOutEdit	BackOutFromDicomEditCompare.pl <?bkgrnd_id?> <sub_invoc_id> <user> <notify>	background_process	\N	{edit_files}	\N	t	0
ImportAndEnsureVisible	ImportAndEnsureVisible.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<path>	{import}	\N	t	0
BackgroundDoProposedEdits	BackgroundDoProposedEdits.pl <?bkgrnd_id?> /nas/public/posda/edited/<rel_dest_root> "<description>" <notify>	background_process	<unmapped_id>&<mapped_id>&<series_instance_uid>&<num_files>&<operations>&<tag>&<val1>&<val2>	{edit_files}	\N	t	0
MakeHierarcyBySeries	GetSeriesHierarchyBySeries.pl <?bkgrnd_id?> <notify>	background_process	<series_instance_uid>	{bills_test}	\N	t	0
DciodvfyReport	BackgroundDciodvfyReport.pl <?bkgrnd_id?> <scan_id> <notify>	background_process	\N	{dciodvfy}	\N	t	0
BackgroundLinkSeriesToStaging	BackgroundLinkSeriesToStaging.pl <?bkgrnd_id?> /nas/public/posda/scratch/staging/<to_rel_dir> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>	{send_series}	\N	t	0
AnonymizerToEditor	AnonymizerToEditor.pl <?bkgrnd_id?> <notify>	background_process	<operation_scope>&<operation>&<tag>&<value1>&<value2>&<patient_id>&<study_instance_uid>&<series_instance_uid>&<unmapped_uid>&<mapped_uid>	{bills_test}	\N	t	0
BackgroundOnlyEditDicomSeries	BackgroundOnlyEditDicomSeries.pl <?bkgrnd_id?> "/nas/public/posda/scratch/staging/<rel_dest_root>" "<desciption>" <notify>	background_process	<unmapped_uid>&<mapped_uid>&<series_instance_uid>&<operation>&<tag>&<val1>&<val2>	{bills_test}	\N	t	0
BackgroundCopySeriesToStaging	BackgroundCopySeriesToStaging.pl <?bkgrnd_id?> /nas/public/posda/scratch/staging/<to_rel_dir> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>	{send_series}	\N	t	0
BackgroundLinkPublicSeries	BackgroundLinkPublicSeries.pl <?bkgrnd_id?> /nas/public/posda/scratch/staging/<to_rel_dir> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>	{send_series}	\N	t	0
MakeRtReport1	MakeRtReport1.pl <?bkgrnd_id?> <notify>	background_process	<collection>&<site>&<patient_id>&<study_uid>&<series_uid>&<file_type>&<modality>&<num_files>	{bills_test}	\N	t	0
FirstPassPhiScanAndReport	FirstPassPhiScanAndReport.pl <?bkgrnd_id?> <collection> <site> "<batch_no>" <notify>	background_process	\N	{bills_test}	\N	t	0
FirstPassPhiByCollection	FirstPassPhiByCollection.pl <?bkgrnd_id?> <collection> <notify>	background_process	\N	{bills_test}	\N	t	0
BackgroundCreateEquivalenceClasses	BackgroundCreateSeriesEquivalenceClasses.pl <?bkgrnd_id?> "<why>" <notify>	background_process	<series_instance_uid>	{visual_review}	\N	t	0
RepealEdits	RepealEdits.pl <?bkgrnd_id?> <subprocess_invoc_id> <notify>	background_process	\N	{find_patients}	\N	t	0
VisualReview	ScheduleVisualReview.pl <?bkgrnd_id?> "<why>" <notify>	background_process	<series_instance_uid>	{visual_review}	\N	t	0
MakeHierarchyBySeries	GetSeriesHierarchyBySeriesWithFileTypeAndModality.pl <?bkgrnd_id?> <notify>	background_process	<series_jnstance_uid>	{bills_test,activity_timepoints}	\N	t	0
NewPhiScanAll	NewPhiScanAll.pl <?bkgrnd_id?> "<description>" <db> <max_lines> <notify>	background_process	<series_uid>	{bills_test,new_workflow}	\N	t	0
MakeHierarchyByPat	GetHierarchyFromPatientId.pl <?bkgrnd_id?> <notify>	background_process	<patient_id>	{bills_test}	\N	t	0
HideEquivalenceClasses	HideEquivalenceClasses.pl <?bkgrnd_id?> <notify>	background_process	<image_equivalence_class_id>&<processing_status>&<review_status>	{visual_review_status}	\N	t	0
MakePassThru	MakePassThru.pl <?bkgrnd_id?> <visual_review_id> <notify>	background_process	<processing_status>&<review_status>&<dicom_file_type>	{visual_review_status}	\N	t	0
ApplyDispositions	BackgroundApplyDispositionsFromVisualScan.pl <?bkgrnd_id?> <dest_dir> <uid_root> <date_offset> <notify>	background_process	<id>&<processing_status>&<review_status>&<dicom_file_type>	{visual_review_status}	\N	t	0
ProcessVisualReview	ProcessVisualReview.pl <?bkgrnd_id?> <scan_id> <notify>	background_process	\N	{visual_review_new_workflow}	\N	t	0
BackgroundHideFiles	BackgroundHideFilesWithStatus.pl <?bkgrnd_id?> <notify> "<reason>"	background_process	<file_id>	{compare_series}	\N	t	0
LinkPublicCollection	LinkPublicCollection.pl <?bkgrnd_id?> <directory> <notify>	background_process	<collection>&<patient_id>&<series_instance_uid>&<dicom_file_uri>	{activity_timepoints,send_series,bills_test}	\N	t	0
BackgroundPrivateDispositions	BackgroundPrivateDispositions.pl <?bkgrnd_id?> <to_dir> <uid_root> <offset> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>	{edit,send_series}	\N	t	0
BackgroundPrivateDispositionsBaseline	BackgroundPrivateDispositionsBaseline.pl <?bkgrnd_id?> <to_dir> <notify>	background_process	<patient_id>&<study_instance_uid>&<series_instance_uid>	{edit,send_series}	\N	t	0
MakeDownloadableDirectory	MakeDownloadableDirectory.pl <?bkgrnd_id?> <sub_dir> <notify>	background_process	<collection>&<patient_id>&<study_instance_uid>&<series_instance_uid>	{send_series}	\N	t	0
BackgroundHideSeries	BackgroundHideSeriesWithIndividualStatus.pl <?bkgrnd_id?> <notify>	background_process	<series_uid>&<reason_to_hide>	{bills_test,new_workflow,activity_support}	\N	t	0
UpdateTimepointAfterEdit	UpdateTimepointAfterEdit.pl <?bkgrnd_id?> <activity_id> <activity_timepoint_id> <subprocess_invocation_id> <notify>	background_process	\N	{update_timepoint,activities}	\N	t	0
AdHocTestSetConversion	AdHocSecondaryCaptureConverter.pl <?bkgrnd_id?> <notify> <source_dir> <dest_dir>	background_process	<pat_code>&<anon_pat_id>&<uid_root>&<pat_sex>	{"Bills Test"}	\N	t	0
AnalyzeSeriesDuplicates	AnalyzeSeriesDuplicates.pl <?bkgrnd_id?> "<collection>" <site> <notify>	background_process	\N	{"ACRIN-FMISO-Brain Duplicate Elimination",dup_sops,activity_timepoint_support}	\N	t	0
BackgroundUnhideFiles	BackgroundUnhideFilesWithStatus.pl <?bkgrnd_id?> <notify> "<reason>"	background_process	<file_id>&<old_visibility>	{activity_timepoint_support}	\N	t	0
ModifySeriesInActivityTp	ModifySeriesInActivityTimepoint.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<series_instance_uid>&<function>	{activity_timepoints}	\N	t	0
UpdateActivityTimepoint	UpdateActivityTimepointForChange.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	\N	{timepoint_buttons}	\N	t	0
InitialAnonymizerCommands	ProduceInitialAnonymizerCommands.pl <?bkgrnd_id?> <collection> <site> <notify>	background_process	<series_instance_uid>&<patient_id>&<patient_name>	{initial_anonymization,patient_mapping}	\N	t	0
HideFilesVisbleInBadEquivalenceClassesByVisualReviewId	HideVisibleFilesInBadIecs.pl <?bkgrnd_id?> <visual_review_instance_id> <notify>	background_process	\N	{visual_review_status}	\N	t	0
BackgroundLinkActivityToTemp	BackgroundLinkActivityToTemp.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	\N	{send_series}	\N	t	0
ProposeEdits	NewProposeEdits.pl <?bkgrnd_id?> <scan_id> <notify>	background_process	<element>%<vr>%<q_value>%<num_series>%<p_op>%<q_arg1>%<q_arg2>	{simple_phi,activity_timepoints}	\N	t	0
BackgroundUnhideSeries	BackgroundUnhideSeriesWithIndividualStatus.pl <?bkgrnd_id?> <notify>	background_process	<series_uid>&<reason_to_unhide>	{bills_test,new_workflow,activity_support}	\N	t	0
MakeDownloadableDirectoryFromSpreadsheet	MakeDownloadableDirectoryFromSpreadsheet.pl <?bkgrnd_id?> <activity_id> <sub_dir> <notify>	background_process	<uploaded_file_name>&<stored_file_name>	{update_timepoint,activities}	\N	t	0
HideEquivalenceClassesTp	HideEquivalenceClassesTp.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<image_equivalence_class_id>&<processing_status>&<review_status>	{visual_review_status}	\N	t	0
SendSeriesToDestination	SendSetOfSeriesToDestination.pl <host> <port> <called> <calling> <user> "<reason>"	legacy	<series_instance_uid>	{send_series}	\N	t	0
UpdateCollectionPrio	UpdateBacklogPriorities.pl	legacy	<collection>&<priority>	{backlog_status}	\N	t	0
RepairBadVrs	RepairBadVrs.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<file_id>	{update_timepoint,activities}	\N	t	0
CompareIntakeFilesToPublicFiles	CompareIntakeFilesToPublicFiles.pl <report_file> <notify>	legacy	<sop_instance_uid> <file_in_intake> <file_in_public>	{compare_collection_site}	\N	t	0
CompareDuplicateSopFirstInSeries	CompareDupSopSeriesList.pl	legacy	<series_instance_uid>	{dup_sops}	\N	t	0
BackgroundCompareDupSops	BackgroundCompareDupSopList.pl <file_name> "<notify>"	legacy	<sop_instance_uid>&<file_id>&<path>&<first_loaded>	{dup_sops}	\N	t	0
BackgroundCompareDuplicateSopFirstInSeries	BackgroundCompareDupSopSeriesList.pl <file_name> "<notify>"	legacy	<series_instance_uid>	{dup_sops}	\N	t	0
TdrAndPhiReports	PrepareTdrAndPhiReport.pl	legacy	<id>&<TdrReportFile>&<PhiReportFile>&<notify>	{phi_review}	\N	t	0
EquivalenceClasses	BatchCreateSeriesEquivalenceClasses.pl <notify>	legacy	<series_instance_uid>	{visual_review}	\N	t	0
BackgroundCompareSopsInMultipleSeries	BackgroundCompareSopsInMultipleSeries.pl <file_name> "<notify>"	legacy	<series_instance_uid>&<sop_instance_uid>&<file_id>&<file_path>	{sops_different_series}	\N	t	0
BulkHashStructUids	BulkHashStructUids.pl <dir> <uid_root> <notify>	legacy	<sop_instance_uid>	{hash_unhashed}	\N	t	0
BulkHashDoseLinks	BulkHashDoseLinks.pl <dir> <uid_root> <notify>	legacy	<sop_instance_uid>	{hash_unhashed}	\N	t	0
ScanDirPhi	PhiDirScan.pl <dir> "<description>"	legacy		{phi_review}	\N	t	0
UpdatePrivateDispositions	UpdatePrivateDisposition.pl <who> "<why>"	legacy	<element_signature>&<vr>&<disposition>	{phi_maint}	\N	t	0
UpdateSimplePrivateDisposition	UpdateSimplePrivateDisposition.pl <who> "<why>"	legacy	<id>&<disp>	{phi_maint}	\N	t	0
HideSeriesWithStatus	HideBatchSeriesWithStatus.pl <who> "<why>"	legacy	<series_instance_uid>	{hide_files,hide_dup_sops}	\N	t	0
HideEarlyDupSopsInSeries	HideBatchEarlySopDupsInSeries.pl <who> "<why>"	legacy	<series_instance_uid>	{hide_files,hide_dup_sops}	\N	t	0
FindSeriesInScanWithPhi	FindSeriesInScanWithPhi.pl <?bkgrnd_id?> <scan_id> <notify>	background_process	<element>&<vr>&<value>&<description>	{simple_phi}	\N	t	0
ApplyPrivateDisposition	CsvApplyPrivateDisposition.pl <dest_dir> <uid_root> <offset> <low_date> <high_date>	legacy	<patient_id>&<study_instance_uid>&<series_instance_uid>	{send_series,apply_disposition}	\N	t	0
MakeSelectedTagValueReport	MakeSelectedTagValueReport.pl /cache/UserData/DbIf/PreparedReports/<report_file_name> <notify>	legacy	<element_signature>&<vr>&<disposition>&<name_chain>&<num_phi_values>&<num_simple_phi_values>	{phi_maint}	\N	t	0
BatchEditBySop	BatchEditDicomFile.pl <?bkgrnd_id?> /nas/public/posda/edited/<rel_dest_root> <who> "<edit_description>" <notify>	background_process	<command>&<arg1>&<arg2>&<arg3>&<arg4>	{edit_files}	\N	t	0
HideFilesWithStatus	HideFilesWithStatus.pl <who> "<why>"	legacy	<file_id>&<old_visibility>	{hide_files,hide_dup_sops}	\N	t	0
ApplyHnsccEdits	ApplyHnsccEdits.pl	legacy	<new_file>&<element>&<new_value>	{}	\N	t	0
ApplyPublicPrivateDisposition	CsvApplyPublicAndPrivateDisposition.pl <dest_dir> <uid_root> <offset> <low_date> <high_date> <sop_class_uid> "<name>"	legacy	<patient_id>&<study_instance_uid>&<series_instance_uid>	{}	\N	t	0
CreatePublicDispositionTable	CreatePublicDispositionTable.pl <sop_class_uid> "<Description>" <who>	legacy	<Tag>^<VR>^<Disposition>^<NameChain>	{}	\N	t	0
LinkFileHierarchy	LinkFileHierarchy.pl <Destination>	legacy	<patient_id>  <study_instance_uid> <series_instance_uid>	{}	\N	t	0
OnlyIn	OnlyIn.pl Posda Intake	legacy	<SeriesInPosda>, <SeriesInIntake>	{}	\N	t	0
PatConsistency	CheckPatConsistency.pl "<collection>" <patient_id>	legacy		{}	\N	t	0
PipeCommand1	PipeCommand1.pl <var1> <var2> 1 2 3	legacy	<vals1>,<vals2>,<vals3>	{}	\N	t	0
SeriesConsistency	CheckSeriesConsistency.pl <series_instance_uid>	legacy		{}	\N	t	0
StudyConsistency	CheckStudyConsistency.pl <study_instance_uid>	legacy		{}	\N	t	0
SymLinkToIntake	SymLinkToIntake.pl /cache/bbennett/Symlinks	legacy	<PID>, <Modality>, <SopInstance>, <FilePath>	{}	\N	t	0
TestCommand	TestCommand.pl <host> <port> <called> <calling> <series_instance_uid>	legacy		{}	\N	t	0
UpdateKnowlegeBase	UpdateKnowledgeBase.pl <who> "<why>"	legacy	<Tag>^<VR>^<Disposition>^<NameChain>	{}	\N	t	0
BatchEditBySop2	BatchEditDicomFile2.pl <?bkgrnd_id?> /cache/UserData/DbIf/PreparedReports/<report_file> /nas/public/posda/edited/<rel_dest_root> <who> "<edit_description>" <notify>	background_process	<command>&<arg1>&<arg2>&<arg3>&<arg4>	{edit_files}	\N	t	0
BackgroundStructLinkageCheck	BackgroundStructLinkageCheck.pl <?bkgrnd_id?> <notify_email>	background_process	<file_id>&<collection>&<site>&<patient_id>&<series_instance_uid>	{background}	\N	t	0
SumPatients	SumPatients.pl <?bkgrnd_id?> "/cache/UserData/DbIf/PreparedReports/<report_file>" <notify>	background_process	<id>&<study>&<series>&<num_files>	{bills_test}	\N	t	0
BackgroundUpdatePrivatedDispositonVr	BackgroundUpdatePrivateDispositionsVr.pl <?bkgrnd_id?> "<why>" <notify>	background_process	<element_sig_pattern>&<vr>&<disp>	{phi_maint}	\N	t	0
TestNewDicomCompare	TestNewDicomCompare.pl <?bkgrnd_id?> <edit_file_id> <notify>	background_process	<sop_instance_uid>&<from_file>&<to_file>	{bills_test}	\N	t	0
CheckCounts	CompareCounts.pl <?bkgrnd_id?> "<collection>" "<site>" <notify>	background_process	<id>&<study>&<series>&<num_files>	{bills_test}	\N	t	0
AddPublicHierarchy	AddHierarchyToSpreadsheetByPublicSop.pl <new_root>	legacy	<file>&<Element>&<OldValue>&<NewValue>	{}	\N	t	0
ImportEditedFiles	ImportEditedFiles.pl <?bkgrnd_id?> <report_file_id> "/cache/UserData/DbIf/PreparedReports/<import_report>" "<edit_comment>" <notify>	background_process	<sop_instance_uid>&<from_digest>&<to_file>&<to_digest>&<status>	{edit_files}	\N	t	0
CheckCounts2	CompareCounts2.pl  <?bkgrnd_id?> "<collection>" <uid_root> "<site>" "<notify>"	background_process	<id>&<study_instance_uid>&<series_instance_uid>&<num_files>	{bills_test}	\N	t	0
FixAcrinFiles	CsvFixAcrin.pl <?bkgrnd_id?> <to_dir> <uid_root> <low_date> <high_date> <notify>	background_process	<patient_id>&<study_uid>&<series_uid>&<offset_pat_id>&<offset>	{bills_test}	\N	t	0
CheckPublicMissingFilesInSeriesByCollection	CheckPublicMissingFilesInSeriesByCollection.pl <?bkgrnd_id?> "<collection>" <notify>	background_process	\N	{bills_test}	\N	t	0
AnnotateCountsSpreadsheet	AnnotateCountsSpreadsheet.pl <?bkgrnd_id?> "<notify>"	background_process	<PID>|<ImageType>|<Modality>|<Images>|<StudyDate>|<StudyDescription>|<SeriesDescription>|<SeriesNumber>|<StudyInstanceUID>|<SeriesInstanceUID>|<Mfr>|<Model>|<software_versions>	{bills_test}	\N	t	0
CopyCollectionToStaging	CopyCollectionToStaging.pl <?bkgrnd_id?> <collection> "/nas/public/posda/scratch/staging/<rel_dir>" <notify>	background_process	\N	{bills_test}	\N	t	0
CheckPosdaPublicConsistency	PublicPosdaCompare.pl <?bkgrnd_id?> <collection>  <notify>	background_process	\N	{public_posda_consistency}	\N	t	0
NewFixAcrinFiles	CsvNewFixAcrin.pl <?bkgrnd_id?> <to_dir> <uid_root> <low_date> <high_date> <notify>	background_process	<patient_id>&<study_uid>&<series_uid>&<sop_instance_uid>&<file_id>&<offset_pat_id>&<offset>	{bills_test}	\N	t	0
PrepareAcrinEdits	PrepareAcrinEdits.pl <?bkgrnd_id?> <notify>	background_process	<ele_pattern>&<value>&<series_instance_uid>	{bills_test}	\N	t	0
QuickCheckPosdaPublicConsistency	QuickPublicPosdaCompare.pl <?bkgrnd_id?> "<collection>"  <notify>	background_process	\N	{public_posda_consistency}	\N	t	0
NewerFixAcrinFiles	CsvNewerFixAcrin.pl <?bkgrnd_id?> <to_dir> <uid_root> <low_date> <high_date> <notify>	background_process	<patient_id>&<study_uid>&<series_uid>&<offset_pat_id>&<offset>	{bills_test}	\N	t	0
FixReallyBadDicomFilesInTimepoint	FixReallyBadDicomFilesInTimepoint.pl <?bkgrnd_id?> <activity_id> <activity_timepoint_id> <notify>	background_process		{ad_hoc_process}	\N	t	0
HideLateDupSopsInSeries	HideBatchLateSopDupsInSeries.pl <who> "<why>"	legacy	<series_instance_uid>	{hide_files,hide_dup_sops}	\N	t	0
BackgroundProcessModules	BackgroundProcessModules.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<file_id>	{dicom_file_type}	\N	t	0
TempMprMakeRotatedAxialFromCoronalStack	TempMprMakeRotatedAxialFromCoronalStack.pl <?bkgrnd_id?> <activity_id> <temp_mpr_volume_id> <notify>	background_process		{temp_mpr}	\N	t	0
CreateActivityTimepoint	CreateActivityTimepoint.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	\N	{visual_review_status}	\N	t	0
CreateActivityTimepointFromCollectionSite	CreateActivityTimepointFromCollectionSite.pl <?bkgrnd_id?> <activity_id> <collection> <site> "<comment>" <notify>	background_process	\N	{timepoint_buttons}	\N	t	0
ListOfAnnotatedFiles	InsertListOfAnnotatedFiles.pl <?bkgrnd_id?> "<comment>" <notify>	background_process	<file_id>&<file_name>&<mime_type>&<description>	{activity_timepoints,send_series_via_dicom,bills_test}	\N	t	0
FixBadSopInstanceLungFusedCtPathology	FixBadSopInstancesLungFusedCtPathology.pl <?bkgrnd_id?> <notify>	background_process	\N	{"Curation of Lung-Fused-CT-Pathology"}	\N	t	0
SummarizeStructLinkage	SummarizeStructLinkagesByFileId.pl <?bkgrnd_id?> <file_id> <notify>	background_process	\N	{activity_timepoint_support}	\N	t	0
StartExportEvent	StartAnExport.pl <?bkgrnd_id?> <activity_id> <export_event_id> "<import_comment>" <notify>	background_process		{export}	\N	t	0
FixFilesWithNullNumberOfFrames	FixFilesWithNullNumberOfFrames.pl <?bkgrnd_id?> "<comment>" <notify>	background_process	\N	{Exceptional-Responders_NCI_Oct2018_curation}	\N	t	0
FixCtInExceptionalRespondersWithNullNumberOfFrames	FixCtErwWithNullNumberOfFrames.pl <?bkgrnd_id?> "<comment>" <notify>	background_process	\N	{Exceptional-Responders_NCI_Oct2018_curation}	\N	t	0
BackgroundEditByStudy	BackgroundEditStudy.pl <?bkgrnd_id?> "<description>" <notify>	background_process	<study_instance_uid>&<op>&<tag>&<val1>&<val2>	{activity_timepoints}	\N	t	0
TestProcessEditByFile	TestProcessBackgroundEditFileInstructions.pl <?bkgrnd_id?> <notify>	background_process	<file_id>&<op>&<tag>&<val1>&<val2>	{testing_edit_objects}	\N	t	0
ReQueueFileNiftiDefacing	ReQueueFileNiftiDefacingTp.pl <?bkgrnd_id?> <activity_id> <notify>	background_subprocess		{nifti}	\N	t	0
BackgroundEditBySop	BackgroundEditDicomFile.pl  <?bkgrnd_id?> /nas/public/posda/edited/<rel_dest_root> <who> "<edit_description>" <notify>	background_process	<command>&<arg1>&<arg2>&<arg3>&<arg4>	{obsolete}	\N	t	0
CompareSopsTpPosdaPublicLike	CompareSopsTpPosdaPublicLike.pl <?bkgrnd_id?> "<collection_like>" <activity_id> <notify>	background_process	\N	{activity_timepoint_support}	\N	t	0
CompareSopsTpPosdaPublicCollectionLikeSiteEqual	CompareSopsTpPosdaPublicLikeEq.pl <?bkgrnd_id?> "<collection_like>" "<site>" <activity_id> <notify>	background_process	\N	{activity_timepoint_support}	\N	t	0
UpdateQualifiedPatients	UpdateQualifiedPatients.pl <?bkgrnd_id?> <notify>	background_process	<collection>&<site>&<patient_id>&<qualified>	{activity_timepoint_support}	\N	t	0
CreateActivityTimepointFromImportName	CreateActivityTimepointFromImportName.pl <?bkgrnd_id?> <activity_id> "<import_name>" "<comment>" <notify>	background_process	\N	{activity_timepoints}	\N	t	0
HelloWorldPython	BackgroundHelloWorldWithInput.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<series_instance_uid>	{foo}	\N	t	0
HideFilesByCollectionSiteAndSeries	HideFilesByCollectionSiteAndSeries.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<collection>&<site>&<series_instance_uid>	{update_timepoint,activities}	\N	t	0
SeriesWithDupSopsDifferentSopClassTp	SeriesWithDupSopsDifferentSopClassTp.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<foo>	{background}	\N	t	0
KeepOnlyFilesDupFilesInTimepointAndSeriesWithMatchingDescriminator	KeepOnlyFilesDupFilesInTimepointAndSeriesWithMatchingDescriminator.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<series_instance_uid>:<descriminator>:<value>	{dup_sops,background}	\N	t	0
BackgroundHideFilesWithStatusTp	BackgroundHideFilesWithStatusTp.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<file_id>&<visibility>	{update_timepoint,activities}	\N	t	0
HideFilesBySeriesAndPatient	BackgroundHideFilesBySeriesAndPatient.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<patient_id>&<series_instance_uid>	{hide_files}	\N	t	0
ExportTimepoint	ExportTimepoint.pl <?bkgrnd_id?> <activity_id> "<destination_name>" "<only_group_13>" "<only_dicom>" "<apply_dispositions>" "<base_line>" "<days_to_shift>" "<uid_root>" <notify>	background_process		{export}	\N	t	0
CloseExportEvent	CloseAnExport.pl <?bkgrnd_id?> <activity_id> "<export_event_id>"  <notify>	background_process		{export}	\N	t	0
ComparePosdaPrivateDataDictToPrivateTagKb	CompareNewPrivateTagDbToOld.pl <?bkgrnd_id?> <activity_id> <notify>	background_process		{private_tag_kb}	\N	t	0
UpdateOrCreatePatientMapping	UpdateOrCreatePatientMapping.pl <?bkgrnd_id?> <activity_id> "<comment>" "<overwrite>" <notify>	background_process	<in_patient_mapping>&<from_patient_id>&<collection>&<site>&<to_patient_id>&<to_patient_name>&<diagnosis_date>&<min_study_date>&<uid_root>&<batch_number>&<site_code>&<baseline_date>&<date_shift>	{patient_mapping}	\N	t	0
SuggestPatientMappings	SuggestPatientMapping.pl <?bkgrnd_id?> <activity_id> "<col_name>" "<crc>" "<site_name>" "<src>" "<date_spec>" "<pat_map_pat>" "<num_dig>" <notify>	background_process		{}	\N	t	0
CreateActivityTimepointFromSopList	CreateActivityTimepointFromSopList.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify>	background_process	<sop_instance_uid>	{activity_timepoints}	\N	t	0
ApplyPrivateDispositionIntake	CsvApplyPrivateDispositionIntake.pl <dest_dir> <uid_root> <offset> <low_date> <high_date>	legacy	<patient_id>&<study_instance_uid>&<series_instance_uid>	{}	\N	t	0
TempMprTempMprProcessAxialResampling	TempMprTempMprProcessAxialResampling.pl <?bkgrnd_id?> <activity_id> <temp_mpr_volume_id> <notify>	background_process	<i_slice_no>&<slice_offset>&<slice_spacing>	{temp_mpr}	\N	t	0
TempMprProcessAxialResampling	TempMprProcessAxialResampling.pl <?bkgrnd_id?> <activity_id> <temp_mpr_volume_id> <notify>	background_process	<i_slice_no>&<slice_offset>&<slice_spacing>	{temp_mpr}	\N	t	0
TempMprMakeIsoTropicCoronalFromAxialStack	TempMprMakeIsoTropicCoronalFromAxialStack.pl <?bkgrnd_id?> <activity_id> <temp_mpr_volume_id> <notify>	background_process		{temp_mpr}	\N	t	0
TempMprPopulateIsoTropicCoronalFromAxialStack	TempMprPopulateIsoTropicCoronalFromAxialStack.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<key>&<value>&<x>&<y>&<z>&<gray_file_id>&<jpeg_file_id>	{temp_mpr}	\N	t	0
TempMprPopulateInitialAxialVolume	TempMprPopulateInitialAxialVolume.pl <?bkgrnd_id?> <activity_id> <series> <notify>	background_process	<file_id>&<pix_rows>&<pix_cols>&<ipp_x>&<ipp_y>&<ipp_z>&<row_spc>&<col_spc>	{temp_mpr}	\N	t	0
TempMprRotateTransposedConronalToSagittal	TempMprRotateTransposedConronalToSagittal.pl <?bkgrnd_id?> <activity_id> <notify>	background_process	<key>,<value>,<x>,<y>,<z>,<gray_file_id>,<jpeg_file_id>	{temp_mpr}	\N	t	0
TempMprTransposeVolume	TempMprTransposeVolume.pl <?bkgrnd_id?> <activity_id> <temp_mpr_volume_id> <notify>	background_process		{temp_mpr}	\N	t	0
BackgroundSingleRtLinkageDetailReports	BackgroundSingleRtLinkageDetailReports.pl <?bkgrnd_id?> <activity_id> <file_path> <notify>	background_process		{StuctLinkages}	\N	t	0
ExportPrivateTagData	ExportPrivateTagData.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{export}	\N	f	0
BackgroundPrivateDispositionsTpDual	BackgroundPrivateDispositionsTpDual.pl <?bkgrnd_id?> <activity_id>  "<notify>" "<skip_dispositions>" "<upd_nbia>" "<dir>"	background_process		{activity_timepoints}	\N	f	0
ImportFromFaspex	ImportFromFaspex.py <?bkgrnd_id?> <activity_id> "<package_dir>" <notify>	background_process		{activity_timepoints}	\N	f	0
NewApplyMasks	NewApplyMasks.py <?bkgrnd_id?> <activity_id> <notify> <visual_review_instance_id> "<process_masks>" "<process_sliceremove>" "<process_blackout>" 	background_process		{export}	\N	f	0
ProduceInitialAnonCmdsFromDeidRecipeTP	ProduceInitialAnonCmdsFromDeidRecipeTP.py <?bkgrnd_id?> <collection> <site> <recipe_file_id> <activity_id> <notify>	background_process		{initial_anonymization,patient_mapping}	\N	f	0
VolumeGeometryReport	VolumeGeometryReport.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{timepoint_buttons}	\N	f	0
FlagVRForMasking	FlagVRForMasking.py <?bkgrnd_id?> <activity_id> <visual_review_instance_id> <notify>	background_process		{visual_review}	\N	f	0
CheckSegLinkages	CheckSegLinkages.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{timepoint_buttons}	\N	f	0
PathologyCreateActivityAndTP	PathologyNewTPfromImport.py <?bkgrnd_id?> "<activity_name>" <import_id> <file_type> <notify>	background_process		{pathology}	\N	f	0
PathologyImageAnalysis	PathologyImageAnalysis.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{pathology}	\N	f	0
PopulateSegBitmaps	PopulateSegBitmaps.pl <?bkgrnd_id?> <notify>	background_process		{}	\N	f	0
ChangeMaskingStatus	ChangeMaskingStatus.py <?bkgrnd_id?> <activity_id> <masking_status> <notify>	background_process	<image_equivalence_class_id>	{masking_status}	\N	f	0
CompareDupSeries	CompareDupSeries.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{}	\N	f	0
CheckLinkages	CheckLinkages.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{timepoint_buttons}	\N	f	0
CopyPriorTimepointExcludingSeries	CopyPriorTimepointExcludingSeries.py <?bkgrnd_id?> <activity_id> <old_tp_id> <notify>	background_process	<series_instance_uid>	{activity_timepoints}	\N	f	0
CopySeriesFromOtherTimepoint	CopySeriesFromOtherTimepoint.py <?bkgrnd_id?> <activity_id> <other_tp_id> <notify>	background_process	<series_instance_uid>	{activity_timepoints}	\N	f	0
ImportPatientMappingWithIds	ImportPatientMappingWithIds.pl <?bkgrnd_id?> <notify>	background_process	<from_patient_id>&<to_patient_id>&<to_patient_name>&<collection_name>&<site_name>&<batch_number>&<date_shift>&<diagnosis_date>&<baseline_date>&<uid_root>&<upload_id>	{mapping_tables,patient_mapping}	\N	f	0
ImportInPlaceFromPublic	ImportInPlaceFromPublic.py <?bkgrnd_id?> <activity_id> <notify> "<collection_name>" "<visibility>" "<site_name>"	background_process		{import}	\N	f	0
Path_Export_parse	PathologyExporter.py <?bkgrnd_id?> <activity_id> <notify>	\N	<root>&<path>&<collectionname>&<studyid>&<clinicaltrialsubjectid>&<imageid>&<fileid>	{pathology,patient_mapping,export}	\N	f	0
CheckRtLinkages	CheckRtLinkages.py <?bkgrnd_id?> <activity_id> <notify>	background_process		{timepoint_buttons}	\N	f	0
ImportPrivateElementSeen	ImportPrivateElementSeen.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<element_sig_pattern>|<tag_name>|<vr>|<private_disposition>	{import}	\N	f	0
ProposeUIDchangeEdits	ProposeUIDchangeEdits.pl <?bkgrnd_id?> <activity_id> <include_series_instance_uid> <include_study_instance_uid> <include_sop> <notify> <description>	background_process		{}	\N	f	0
ChangeReviewStatus	ChangeReviewStatus.pl <?bkgrnd_id?> <activity_id> <review_status> <processing_status> <notify>	background_process	<image_equivalence_class_id>&<processing_status>&<review_status>	{visual_review_status}	\N	f	0
Path_Patient_Mapping	PathologyCreatePatientMapping.py <?bkgrnd_id?> <activity_id> <notify>	background_process	<patient_id>&<original_file_name>&<collection_name>&<site_name>&<study_name>&<image_id>&<clinical_trial_subject_id>&<shift_date>&<base_date>&<reg_date>	{pathology,patient_mapping}	\N	f	0
\.


--
-- Name: apps_app_id_seq; Type: SEQUENCE SET; Schema: auth; Owner: -
--

SELECT pg_catalog.setval('auth.apps_app_id_seq', 13, true);


--
-- Name: permissions_permission_id_seq; Type: SEQUENCE SET; Schema: auth; Owner: -
--

SELECT pg_catalog.setval('auth.permissions_permission_id_seq', 60, true);


--
-- Name: users_user_id_seq; Type: SEQUENCE SET; Schema: auth; Owner: -
--

SELECT pg_catalog.setval('auth.users_user_id_seq', 32, true);


--
-- Name: background_buttons_background_button_id_seq; Type: SEQUENCE SET; Schema: dbif_config; Owner: -
--

SELECT pg_catalog.setval('dbif_config.background_buttons_background_button_id_seq', 56, true);


--
-- Name: chained_query_chained_query_id_seq; Type: SEQUENCE SET; Schema: dbif_config; Owner: -
--

SELECT pg_catalog.setval('dbif_config.chained_query_chained_query_id_seq', 22, true);


--
-- Name: popup_buttons_popup_button_id_seq1; Type: SEQUENCE SET; Schema: dbif_config; Owner: -
--

SELECT pg_catalog.setval('dbif_config.popup_buttons_popup_button_id_seq1', 75, true);


--
-- PostgreSQL database dump complete
--

\unrestrict mSgwALpYGku8jHAyVF4SFoL8l2nVlooKhvfKbo9ZpEsHlnSJhYKbIF0IVngs7OH

