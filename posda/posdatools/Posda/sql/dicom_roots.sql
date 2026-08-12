--
-- PostgreSQL database dump
--

\restrict U2ESg4o7l1MVetn0jqGeftpwTaZZbxBzbjfpOhA8d8UX90Ew60wn7heJfTGQIFW

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
-- Name: dicom_roots; Type: DATABASE; Schema: -; Owner: -
--

CREATE DATABASE dicom_roots WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'en_US.UTF-8';


\unrestrict U2ESg4o7l1MVetn0jqGeftpwTaZZbxBzbjfpOhA8d8UX90Ew60wn7heJfTGQIFW
\connect dicom_roots
\restrict U2ESg4o7l1MVetn0jqGeftpwTaZZbxBzbjfpOhA8d8UX90Ew60wn7heJfTGQIFW

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
-- Name: version; Type: TABLE; Schema: db_version; Owner: -
--

CREATE TABLE db_version.version (
    version integer
);


--
-- Name: collection; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection (
    collection_id integer NOT NULL,
    collection_code text
);


--
-- Name: collection_collection_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.collection_collection_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: collection_collection_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.collection_collection_id_seq OWNED BY public.collection.collection_id;


--
-- Name: site; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.site (
    site_id integer NOT NULL,
    site_code text
);


--
-- Name: site_site_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.site_site_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: site_site_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.site_site_id_seq OWNED BY public.site.site_id;


--
-- Name: submission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.submission (
    submission_id integer NOT NULL,
    collection_id integer NOT NULL,
    site_id integer NOT NULL,
    collection_name text,
    site_name text,
    body_part_entered text,
    patient_id_prefix text,
    access_type text,
    date_inc text,
    extra text
);


--
-- Name: submission_submission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.submission_submission_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: submission_submission_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.submission_submission_id_seq OWNED BY public.submission.submission_id;


--
-- Name: submissionevent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.submissionevent (
    submission_id integer NOT NULL,
    event_type text,
    occurance_date_time timestamp with time zone,
    reporting_user text,
    comment text
);


--
-- Name: collection collection_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection ALTER COLUMN collection_id SET DEFAULT nextval('public.collection_collection_id_seq'::regclass);


--
-- Name: site site_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site ALTER COLUMN site_id SET DEFAULT nextval('public.site_site_id_seq'::regclass);


--
-- Name: submission submission_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submission ALTER COLUMN submission_id SET DEFAULT nextval('public.submission_submission_id_seq'::regclass);


--
-- Name: collection collection_collection_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT collection_collection_code_key UNIQUE (collection_code);


--
-- Name: site site_site_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site
    ADD CONSTRAINT site_site_code_key UNIQUE (site_code);


--
-- PostgreSQL database dump complete
--

\unrestrict U2ESg4o7l1MVetn0jqGeftpwTaZZbxBzbjfpOhA8d8UX90Ew60wn7heJfTGQIFW

