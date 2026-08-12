--
-- PostgreSQL database dump
--

\restrict nd6H1cqu1e39oXtCRJR8BuMDBWVjjbBZ6QECRoYe8EWLBHlmIvlrc364ajzArTh

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
-- Name: public_tag_disposition; Type: DATABASE; Schema: -; Owner: -
--

CREATE DATABASE public_tag_disposition WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'en_US.UTF-8';


\unrestrict nd6H1cqu1e39oXtCRJR8BuMDBWVjjbBZ6QECRoYe8EWLBHlmIvlrc364ajzArTh
\connect public_tag_disposition
\restrict nd6H1cqu1e39oXtCRJR8BuMDBWVjjbBZ6QECRoYe8EWLBHlmIvlrc364ajzArTh

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: public_tag_disposition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_tag_disposition (
    tag_name text,
    name text,
    disposition text
);


--
-- Name: public_tag_disposition public_tag_disposition_tag_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_tag_disposition
    ADD CONSTRAINT public_tag_disposition_tag_name_key UNIQUE (tag_name);


--
-- PostgreSQL database dump complete
--

\unrestrict nd6H1cqu1e39oXtCRJR8BuMDBWVjjbBZ6QECRoYe8EWLBHlmIvlrc364ajzArTh

