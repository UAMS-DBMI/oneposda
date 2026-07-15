# Masking VR Filtering — Working Notes

Team-shared planning notes for the masking-review filtering feature.

## Overview

Added a filtering mechanism to
[posda/fastapi/app/papi/routes/masking.py](../posda/fastapi/app/papi/routes/masking.py),
modeled directly on the existing filtering mechanism for DICOM visual review in
[posda/fastapi/app/papi/routes/visualreviews.py](../posda/fastapi/app/papi/routes/visualreviews.py)
(`GET /{vr}/values` + `POST /{vr}/filter`).

**Design decision:** added as new routes rather than modifying the existing
`GET /visualreview/{visual_review_instance_id}` endpoint (which takes a simple
`awaiting_review: bool` query param) — that endpoint is left untouched for backward
compatibility. The new mechanism lives alongside it, same pattern as `visualreviews.py`
having both an unfiltered `GET /{vr}/iecs` and a filtered `POST /{vr}/filter`.

## What was added

- `GET /visualreview/{visual_review_instance_id}/values` — returns valid filter values
  (with counts) for `dicom_file_type` and `masking_status`, scoped to IECs in this VR that
  are flagged for masking (i.e., present in the `masking` table). Mirrors
  `visualreviews.py`'s `GET /{vr}/values` exactly, including the "0 results → check VR
  validity → 404 if not found" fallback.
- `POST /visualreview/{visual_review_instance_id}/filter` — accepts a
  `MaskingFilterParameters` body (`dicom_file_type`, `masking_status`, both
  `Optional[str] = '*'` — `'*'` is wildcard, `None` filters for SQL `NULL`), returns a
  filtered, ascending-order list of IEC ids. Mirrors `visualreviews.py`'s
  `POST /{vr}/filter` exactly, including the dynamic bind-var query building and the same
  0-results/404 fallback.

## Filter field choice

Scoped to `masking_status` and `dicom_file_type` only — deliberately **not** `review_status`
or `processing_status` (the two other fields VR filters on).

- `masking_status` is the direct masking-specific analog of VR's `processing_status` — it's
  the status column on the `masking` table itself (`created`, `ready-to-process`,
  `in-process`, `process-complete`, `errored`, `accepted`, `rejected`, `skipped`,
  `nonmaskable`).
- `dicom_file_type` carries over identically — same derivation
  (`image_equivalence_class_input_image natural join dicom_file`), same underlying
  `image_equivalence_class` table, so the query logic is copy-paste-equivalent.
- `review_status`/`processing_status` (columns on `image_equivalence_class` itself, used by
  VR) describe DICOM visual-review state, not masking state — including them here would mix
  two different review concerns. Left out; revisit if there's an actual use case for
  cross-filtering by VR review state within the masking queue.

## Open questions

- [ ] Should the existing `GET /visualreview/{id}?awaiting_review=bool` route eventually be
      deprecated in favor of `POST .../filter` with `masking_status` set explicitly (e.g.
      `masking_status: 'process-complete'` for "awaiting review")? Left as-is for now per the
      backward-compatibility decision above — no caller was asked to migrate.
- [ ] Confirm whether `review_status`/`processing_status` filtering is ever actually wanted
      in the masking queue before adding it — scoped out above as likely out of concern,
      not confirmed unnecessary.
