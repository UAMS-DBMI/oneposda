--
-- PostgreSQL database dump
--

\restrict 6dalNtbfbmMVzsJOZnicfhwi8e8kZdEHQzpaNNM4DwcjvQv0e7OGvFZTzijEZxX

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
-- Name: posda_phi_simple; Type: DATABASE; Schema: -; Owner: -
--

CREATE DATABASE posda_phi_simple WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'en_US.UTF-8';


\unrestrict 6dalNtbfbmMVzsJOZnicfhwi8e8kZdEHQzpaNNM4DwcjvQv0e7OGvFZTzijEZxX
\connect posda_phi_simple
\restrict 6dalNtbfbmMVzsJOZnicfhwi8e8kZdEHQzpaNNM4DwcjvQv0e7OGvFZTzijEZxX

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
-- Name: db_version; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA db_version;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: migration; Type: TABLE; Schema: db_version; Owner: -
--

CREATE TABLE db_version.migration (
    filename text NOT NULL,
    sha256 text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_by text DEFAULT CURRENT_USER NOT NULL
);


--
-- Name: version; Type: TABLE; Schema: db_version; Owner: -
--

CREATE TABLE db_version.version (
    version integer
);


--
-- Name: dciodvfy_error; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dciodvfy_error (
    dciodvfy_error_id integer NOT NULL,
    error_type text NOT NULL,
    error_tag text,
    error_value text,
    error_subtype text,
    error_module text,
    error_reason text,
    error_index text,
    error_text text
);


--
-- Name: dciodvfy_error_dciodvfy_error_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dciodvfy_error_dciodvfy_error_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dciodvfy_error_dciodvfy_error_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dciodvfy_error_dciodvfy_error_id_seq OWNED BY public.dciodvfy_error.dciodvfy_error_id;


--
-- Name: dciodvfy_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dciodvfy_scan_instance (
    dciodvfy_scan_instance_id integer NOT NULL,
    type_of_unit text,
    description_of_scan text,
    number_units integer,
    scanned_so_far integer,
    start_time timestamp with time zone,
    end_time timestamp with time zone
);


--
-- Name: dciodvfy_scan_instance_dciodvfy_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dciodvfy_scan_instance_dciodvfy_scan_instance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dciodvfy_scan_instance_dciodvfy_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dciodvfy_scan_instance_dciodvfy_scan_instance_id_seq OWNED BY public.dciodvfy_scan_instance.dciodvfy_scan_instance_id;


--
-- Name: dciodvfy_unit_scan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dciodvfy_unit_scan (
    dciodvfy_unit_scan_id integer NOT NULL,
    type_of_unit text,
    unit_uid text,
    unit_id integer,
    num_file_in_unit integer,
    num_errors_in_unit integer,
    num_warnings_in_unit integer,
    start_time timestamp with time zone,
    end_time timestamp with time zone
);


--
-- Name: dciodvfy_unit_scan_dciodvfy_unit_scan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dciodvfy_unit_scan_dciodvfy_unit_scan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dciodvfy_unit_scan_dciodvfy_unit_scan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dciodvfy_unit_scan_dciodvfy_unit_scan_id_seq OWNED BY public.dciodvfy_unit_scan.dciodvfy_unit_scan_id;


--
-- Name: dciodvfy_unit_scan_error; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dciodvfy_unit_scan_error (
    dciodvfy_scan_instance_id integer NOT NULL,
    dciodvfy_unit_scan_id integer NOT NULL,
    dciodvfy_error_id integer NOT NULL
);


--
-- Name: dciodvfy_unit_scan_warning; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dciodvfy_unit_scan_warning (
    dciodvfy_scan_instance_id integer NOT NULL,
    dciodvfy_unit_scan_id integer NOT NULL,
    dciodvfy_warning_id integer NOT NULL
);


--
-- Name: dciodvfy_warning; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dciodvfy_warning (
    dciodvfy_warning_id integer NOT NULL,
    warning_type text NOT NULL,
    warning_tag text,
    warning_desc text,
    warning_iod text,
    warning_comment text,
    warning_value text,
    warning_reason text,
    warning_index text,
    warning_text text
);


--
-- Name: dciodvfy_warning_dciodvfy_warning_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dciodvfy_warning_dciodvfy_warning_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dciodvfy_warning_dciodvfy_warning_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dciodvfy_warning_dciodvfy_warning_id_seq OWNED BY public.dciodvfy_warning.dciodvfy_warning_id;


--
-- Name: element_disposition_changed; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.element_disposition_changed (
    element_seen_id integer NOT NULL,
    when_changed timestamp with time zone,
    who_changed text,
    why_changed text,
    new_disposition text
);


--
-- Name: element_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.element_seen (
    element_seen_id integer NOT NULL,
    element_sig_pattern text,
    vr text,
    is_private boolean,
    tag_name text,
    private_disposition text
);


--
-- Name: element_seen_element_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.element_seen_element_seen_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: element_seen_element_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.element_seen_element_seen_id_seq OWNED BY public.element_seen.element_seen_id;


--
-- Name: element_value_occurance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.element_value_occurance (
    element_seen_id integer NOT NULL,
    value_seen_id integer NOT NULL,
    series_scan_instance_id integer NOT NULL,
    phi_scan_instance_id integer NOT NULL
);


--
-- Name: nifti_phi_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nifti_phi_scan_instance (
    nifti_phi_scan_instance_id integer NOT NULL,
    description text NOT NULL,
    start_time timestamp with time zone,
    end_time timestamp with time zone
);


--
-- Name: nifti_phi_scan_instance_nifti_phi_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nifti_phi_scan_instance_nifti_phi_scan_instance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nifti_phi_scan_instance_nifti_phi_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nifti_phi_scan_instance_nifti_phi_scan_instance_id_seq OWNED BY public.nifti_phi_scan_instance.nifti_phi_scan_instance_id;


--
-- Name: nifti_tag_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nifti_tag_seen (
    nifti_tag_seen_id integer NOT NULL,
    tag_name text
);


--
-- Name: nifti_tag_seen_nifti_tag_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nifti_tag_seen_nifti_tag_seen_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nifti_tag_seen_nifti_tag_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nifti_tag_seen_nifti_tag_seen_id_seq OWNED BY public.nifti_tag_seen.nifti_tag_seen_id;


--
-- Name: nifti_tag_value_occurrence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nifti_tag_value_occurrence (
    nifti_tag_seen_id integer NOT NULL,
    nifti_value_seen_id integer NOT NULL,
    nifti_phi_scan_instance_id integer NOT NULL,
    file_id integer NOT NULL
);


--
-- Name: nifti_value_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nifti_value_seen (
    nifti_value_seen_id integer NOT NULL,
    value text NOT NULL
);


--
-- Name: nifti_value_seen_nifti_value_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nifti_value_seen_nifti_value_seen_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nifti_value_seen_nifti_value_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nifti_value_seen_nifti_value_seen_id_seq OWNED BY public.nifti_value_seen.nifti_value_seen_id;


--
-- Name: non_dicom_file_scan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.non_dicom_file_scan (
    non_dicom_file_scan_id integer NOT NULL,
    phi_non_dicom_scan_instance_id integer NOT NULL,
    file_type text NOT NULL,
    file_in_posda boolean,
    file_in_wrapped_tgz boolean,
    posda_file_id integer,
    rel_path text,
    sop_instance_uid text
);


--
-- Name: non_dicom_file_scan_non_dicom_file_scan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.non_dicom_file_scan_non_dicom_file_scan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: non_dicom_file_scan_non_dicom_file_scan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.non_dicom_file_scan_non_dicom_file_scan_id_seq OWNED BY public.non_dicom_file_scan.non_dicom_file_scan_id;


--
-- Name: non_dicom_path_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.non_dicom_path_seen (
    non_dicom_path_seen_id integer NOT NULL,
    non_dicom_file_type text,
    non_dicom_path text
);


--
-- Name: non_dicom_path_seen_non_dicom_path_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.non_dicom_path_seen_non_dicom_path_seen_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: non_dicom_path_seen_non_dicom_path_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.non_dicom_path_seen_non_dicom_path_seen_id_seq OWNED BY public.non_dicom_path_seen.non_dicom_path_seen_id;


--
-- Name: non_dicom_path_value_occurrance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.non_dicom_path_value_occurrance (
    non_dicom_path_seen_id integer NOT NULL,
    value_seen_id integer NOT NULL,
    non_dicom_file_scan_id integer NOT NULL
);


--
-- Name: phi_non_dicom_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.phi_non_dicom_scan_instance (
    phi_non_dicom_scan_instance_id integer CONSTRAINT phi_non_dicom_scan_instance_phi_non_dicom_scan_instanc_not_null NOT NULL,
    pndsi_description text,
    pndsi_start_time timestamp with time zone,
    pndsi_num_files integer,
    pndsi_num_files_scanned integer,
    pndsi_end_time timestamp with time zone,
    pndsi_process_pid integer
);


--
-- Name: phi_non_dicom_scan_instance_phi_non_dicom_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.phi_non_dicom_scan_instance_phi_non_dicom_scan_instance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: phi_non_dicom_scan_instance_phi_non_dicom_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.phi_non_dicom_scan_instance_phi_non_dicom_scan_instance_id_seq OWNED BY public.phi_non_dicom_scan_instance.phi_non_dicom_scan_instance_id;


--
-- Name: phi_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.phi_scan_instance (
    phi_scan_instance_id integer NOT NULL,
    description text NOT NULL,
    start_time timestamp with time zone,
    num_series integer,
    num_series_scanned integer,
    end_time timestamp with time zone,
    file_query text
);


--
-- Name: phi_scan_instance_phi_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.phi_scan_instance_phi_scan_instance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: phi_scan_instance_phi_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.phi_scan_instance_phi_scan_instance_id_seq OWNED BY public.phi_scan_instance.phi_scan_instance_id;


--
-- Name: series_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.series_scan_instance (
    series_scan_instance_id integer NOT NULL,
    scan_instance_id integer NOT NULL,
    series_instance_uid text NOT NULL,
    num_files integer,
    start_time timestamp with time zone,
    end_time timestamp with time zone
);


--
-- Name: series_scan_instance_series_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.series_scan_instance_series_scan_instance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: series_scan_instance_series_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.series_scan_instance_series_scan_instance_id_seq OWNED BY public.series_scan_instance.series_scan_instance_id;


--
-- Name: sr_path_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sr_path_seen (
    sr_path_seen_id integer NOT NULL,
    path_sig_pattern text
);


--
-- Name: sr_path_seen_sr_path_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sr_path_seen_sr_path_seen_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sr_path_seen_sr_path_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sr_path_seen_sr_path_seen_id_seq OWNED BY public.sr_path_seen.sr_path_seen_id;


--
-- Name: sr_path_value_occurance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sr_path_value_occurance (
    sr_path_seen_id integer NOT NULL,
    value_seen_id integer NOT NULL,
    tag text,
    sr_series_scan_instance_id text NOT NULL,
    sr_phi_scan_instance_id integer NOT NULL
);


--
-- Name: sr_phi_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sr_phi_scan_instance (
    sr_phi_scan_instance_id integer NOT NULL,
    description text NOT NULL,
    start_time timestamp with time zone,
    end_time timestamp with time zone
);


--
-- Name: sr_phi_scan_instance_sr_phi_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sr_phi_scan_instance_sr_phi_scan_instance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sr_phi_scan_instance_sr_phi_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sr_phi_scan_instance_sr_phi_scan_instance_id_seq OWNED BY public.sr_phi_scan_instance.sr_phi_scan_instance_id;


--
-- Name: tiff_phi_scan_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tiff_phi_scan_instance (
    tiff_phi_scan_instance_id integer NOT NULL,
    description text NOT NULL,
    start_time timestamp with time zone,
    end_time timestamp with time zone
);


--
-- Name: tiff_phi_scan_instance_tiff_phi_scan_instance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tiff_phi_scan_instance_tiff_phi_scan_instance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tiff_phi_scan_instance_tiff_phi_scan_instance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tiff_phi_scan_instance_tiff_phi_scan_instance_id_seq OWNED BY public.tiff_phi_scan_instance.tiff_phi_scan_instance_id;


--
-- Name: tiff_tag_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tiff_tag_seen (
    tiff_tag_seen_id integer NOT NULL,
    is_private boolean,
    tag_name text
);


--
-- Name: tiff_tag_seen_tiff_tag_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tiff_tag_seen_tiff_tag_seen_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tiff_tag_seen_tiff_tag_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tiff_tag_seen_tiff_tag_seen_id_seq OWNED BY public.tiff_tag_seen.tiff_tag_seen_id;


--
-- Name: tiff_tag_value_occurrence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tiff_tag_value_occurrence (
    tiff_tag_seen_id integer NOT NULL,
    tiff_value_seen_id integer NOT NULL,
    tiff_phi_scan_instance_id integer NOT NULL,
    file_id integer NOT NULL,
    page_id integer NOT NULL
);


--
-- Name: tiff_value_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tiff_value_seen (
    tiff_value_seen_id integer NOT NULL,
    value text NOT NULL
);


--
-- Name: tiff_value_seen_tiff_value_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tiff_value_seen_tiff_value_seen_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tiff_value_seen_tiff_value_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tiff_value_seen_tiff_value_seen_id_seq OWNED BY public.tiff_value_seen.tiff_value_seen_id;


--
-- Name: value_seen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.value_seen (
    value_seen_id integer NOT NULL,
    value text NOT NULL
);


--
-- Name: value_seen_value_seen_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.value_seen_value_seen_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: value_seen_value_seen_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.value_seen_value_seen_id_seq OWNED BY public.value_seen.value_seen_id;


--
-- Name: dciodvfy_error dciodvfy_error_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dciodvfy_error ALTER COLUMN dciodvfy_error_id SET DEFAULT nextval('public.dciodvfy_error_dciodvfy_error_id_seq'::regclass);


--
-- Name: dciodvfy_scan_instance dciodvfy_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dciodvfy_scan_instance ALTER COLUMN dciodvfy_scan_instance_id SET DEFAULT nextval('public.dciodvfy_scan_instance_dciodvfy_scan_instance_id_seq'::regclass);


--
-- Name: dciodvfy_unit_scan dciodvfy_unit_scan_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dciodvfy_unit_scan ALTER COLUMN dciodvfy_unit_scan_id SET DEFAULT nextval('public.dciodvfy_unit_scan_dciodvfy_unit_scan_id_seq'::regclass);


--
-- Name: dciodvfy_warning dciodvfy_warning_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dciodvfy_warning ALTER COLUMN dciodvfy_warning_id SET DEFAULT nextval('public.dciodvfy_warning_dciodvfy_warning_id_seq'::regclass);


--
-- Name: element_seen element_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.element_seen ALTER COLUMN element_seen_id SET DEFAULT nextval('public.element_seen_element_seen_id_seq'::regclass);


--
-- Name: nifti_phi_scan_instance nifti_phi_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nifti_phi_scan_instance ALTER COLUMN nifti_phi_scan_instance_id SET DEFAULT nextval('public.nifti_phi_scan_instance_nifti_phi_scan_instance_id_seq'::regclass);


--
-- Name: nifti_tag_seen nifti_tag_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nifti_tag_seen ALTER COLUMN nifti_tag_seen_id SET DEFAULT nextval('public.nifti_tag_seen_nifti_tag_seen_id_seq'::regclass);


--
-- Name: nifti_value_seen nifti_value_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nifti_value_seen ALTER COLUMN nifti_value_seen_id SET DEFAULT nextval('public.nifti_value_seen_nifti_value_seen_id_seq'::regclass);


--
-- Name: non_dicom_file_scan non_dicom_file_scan_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.non_dicom_file_scan ALTER COLUMN non_dicom_file_scan_id SET DEFAULT nextval('public.non_dicom_file_scan_non_dicom_file_scan_id_seq'::regclass);


--
-- Name: non_dicom_path_seen non_dicom_path_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.non_dicom_path_seen ALTER COLUMN non_dicom_path_seen_id SET DEFAULT nextval('public.non_dicom_path_seen_non_dicom_path_seen_id_seq'::regclass);


--
-- Name: phi_non_dicom_scan_instance phi_non_dicom_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phi_non_dicom_scan_instance ALTER COLUMN phi_non_dicom_scan_instance_id SET DEFAULT nextval('public.phi_non_dicom_scan_instance_phi_non_dicom_scan_instance_id_seq'::regclass);


--
-- Name: phi_scan_instance phi_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.phi_scan_instance ALTER COLUMN phi_scan_instance_id SET DEFAULT nextval('public.phi_scan_instance_phi_scan_instance_id_seq'::regclass);


--
-- Name: series_scan_instance series_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.series_scan_instance ALTER COLUMN series_scan_instance_id SET DEFAULT nextval('public.series_scan_instance_series_scan_instance_id_seq'::regclass);


--
-- Name: sr_path_seen sr_path_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sr_path_seen ALTER COLUMN sr_path_seen_id SET DEFAULT nextval('public.sr_path_seen_sr_path_seen_id_seq'::regclass);


--
-- Name: sr_phi_scan_instance sr_phi_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sr_phi_scan_instance ALTER COLUMN sr_phi_scan_instance_id SET DEFAULT nextval('public.sr_phi_scan_instance_sr_phi_scan_instance_id_seq'::regclass);


--
-- Name: tiff_phi_scan_instance tiff_phi_scan_instance_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tiff_phi_scan_instance ALTER COLUMN tiff_phi_scan_instance_id SET DEFAULT nextval('public.tiff_phi_scan_instance_tiff_phi_scan_instance_id_seq'::regclass);


--
-- Name: tiff_tag_seen tiff_tag_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tiff_tag_seen ALTER COLUMN tiff_tag_seen_id SET DEFAULT nextval('public.tiff_tag_seen_tiff_tag_seen_id_seq'::regclass);


--
-- Name: tiff_value_seen tiff_value_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tiff_value_seen ALTER COLUMN tiff_value_seen_id SET DEFAULT nextval('public.tiff_value_seen_tiff_value_seen_id_seq'::regclass);


--
-- Name: value_seen value_seen_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.value_seen ALTER COLUMN value_seen_id SET DEFAULT nextval('public.value_seen_value_seen_id_seq'::regclass);


--
-- Name: migration migration_pkey; Type: CONSTRAINT; Schema: db_version; Owner: -
--

ALTER TABLE ONLY db_version.migration
    ADD CONSTRAINT migration_pkey PRIMARY KEY (filename);


--
-- Name: nifti_tag_seen nifti_tag_seen_tag_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nifti_tag_seen
    ADD CONSTRAINT nifti_tag_seen_tag_key UNIQUE (tag_name);


--
-- Name: nifti_value_seen nifti_value_seen_value_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nifti_value_seen
    ADD CONSTRAINT nifti_value_seen_value_key UNIQUE (value);


--
-- Name: tiff_tag_seen tiff_tag_seen_tag_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tiff_tag_seen
    ADD CONSTRAINT tiff_tag_seen_tag_key UNIQUE (tag_name);


--
-- Name: tiff_value_seen tiff_value_seen_value_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tiff_value_seen
    ADD CONSTRAINT tiff_value_seen_value_key UNIQUE (value);


--
-- Name: value_seen value_seen_value_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.value_seen
    ADD CONSTRAINT value_seen_value_key UNIQUE (value);


--
-- Name: element_seen_and_value_seen_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX element_seen_and_value_seen_index ON public.element_value_occurance USING btree (element_seen_id, value_seen_id);


--
-- Name: element_seen_vr_pair_index; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX element_seen_vr_pair_index ON public.element_seen USING btree (element_sig_pattern, vr);


--
-- Name: sr_path_seen_and_value_seen_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sr_path_seen_and_value_seen_index ON public.sr_path_value_occurance USING btree (sr_path_seen_id, value_seen_id);


--
-- PostgreSQL database dump complete
--

\unrestrict 6dalNtbfbmMVzsJOZnicfhwi8e8kZdEHQzpaNNM4DwcjvQv0e7OGvFZTzijEZxX

