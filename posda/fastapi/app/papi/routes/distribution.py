from fastapi import Depends, APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import asyncio
import asyncpg
import csv
import hashlib
import httpx
import io
import os
import secrets
import tempfile
from .auth import logged_in_user, User
from . import importer

from ..util import Database
from ..util.wp import wp_get, wp_url, wp_client

FILE_STORAGE_PATH = os.getenv("FILE_STORAGE_PATH", "/home/posda/cache/created")
FILE_STORAGE_ROOT = int(os.getenv("FILE_STORAGE_ROOT_ID", "3"))
IDC_TRANSFER_BUCKET = os.getenv("IDC_TRANSFER_BUCKET", "posda_submit")

# What IDC can house, written as the file properties themselves rather than as a
# proxy for them. IDC ingests DICOM whatever it depicts -- radiology, pathology
# slides, SEG/RT annotations -- so keying imaging off recordset_type was only
# ever standing in for "is it DICOM", which pathology DICOM breaks. "Clinical"
# means the tabular data IDC parses, which is what the Clinical Data recordset
# type denotes; deriving it from "not DICOM" swept in anything non-DICOM that is
# not clinical at all (a histopathology bundle bound for Aspera, say).
#
# Both are null-safe (`is true` / `is not true`), so together they partition
# every file in a transfer into exactly three groups: imaging, clinical, and
# neither. A file in the third group is a routing mistake, not a category.
#
# Shared so the manifests, the queue gate and the transfer_file fan-out cannot
# drift apart. A file listed in a manifest but never uploaded -- or uploaded
# with no manifest row -- is the failure this whole scheme exists to prevent.
# Every query using them needs `file f` and `recordset_type rt` in scope.
IDC_IMAGING_PREDICATE  = "f.is_dicom_file is true"
IDC_CLINICAL_PREDICATE = (
    "f.is_dicom_file is not true and rt.recordset_type_name = 'Clinical Data'"
)

router = APIRouter(
    tags=["Distribution"],
    dependencies=[logged_in_user]
)

# --- Models ---

class DatasetInsert(BaseModel):
    dataset_type_id: int
    dataset_name: str
    dataset_doi: str
    active: bool = True

class DatasetUpdate(BaseModel):
    dataset_type_id: Optional[int] = None
    dataset_name: Optional[str] = None
    dataset_doi: Optional[str] = None
    active: Optional[bool] = None

class DatasetReleaseInsert(BaseModel):
    # Omit to auto-assign the next unused number for this dataset -- lets
    # "start next cycle" create a draft release without asking for one.
    release_number: Optional[int] = None
    # Null while draft -- set when release_status transitions to 'released'
    # (either explicitly here, or auto-stamped by update_dataset_release).
    release_date: Optional[datetime] = None
    release_notes: Optional[str] = None
    release_doi: Optional[str] = None
    release_status: Optional[str] = "draft"

class DatasetReleaseUpdate(BaseModel):
    dataset_id: Optional[int] = None
    release_number: Optional[int] = None
    release_date: Optional[datetime] = None
    release_notes: Optional[str] = None
    release_doi: Optional[str] = None
    release_status: Optional[str] = None

class DatasetReleaseRecordsetRequest(BaseModel):
    recordset_release_ids: list[int]

class DatasetReleaseTransferInsert(BaseModel):
    destination_id: int
    transfer_name: str
    transfer_mode_id: int
    transfer_notes: Optional[str] = None
    transfer_status: Optional[str] = "draft"
    recordset_release_ids: Optional[list[int]] = None

class RecordsetUpdate(BaseModel):
    recordset_doi: Optional[str] = None
    dataset_id: Optional[int] = None
    license_id: Optional[int] = None
    recordset_name: Optional[str] = None
    recordset_type_id: Optional[int] = None
    active: Optional[bool] = None

class RecordsetCreate(BaseModel):
    recordset_doi: Optional[str] = None
    dataset_id: int
    license_id: int
    recordset_type_id: int
    recordset_name: str
    active: bool = True

class DestinationUpdate(BaseModel):
    default_display: Optional[bool] = None
    default_transfer_mode_id: Optional[int] = None

class RecordsetDraftInsert(BaseModel):
    # Name is optional -- auto-generated ("Version N Draft" / "Initial Draft")
    # when omitted. A draft has a single source: an activity timepoint, a
    # release to clone, or neither (empty). The two source fields are mutually
    # exclusive.
    draft_name: Optional[str] = None
    draft_status: Optional[str] = "open"
    draft_notes:  Optional[str] = None
    cloned_from_release_id: Optional[int] = None
    activity_timepoint_id: Optional[int] = None

class RecordsetDraftUpdate(BaseModel):
    recordset_id: Optional[int] = None
    draft_name: Optional[str] = None
    draft_notes:  Optional[str] = None
    draft_status: Optional[str] = "open"
    cloned_from_release_id: Optional[int] = None

class RecordsetDraftFileItem(BaseModel):
    file_id: int
    # Optional -- when omitted, sourced from file_import for non-DICOM files
    # (DICOM stays null). The same file_id may appear multiple times in one
    # request under different names (content-identical files, e.g. blank
    # segmentations for different subjects).
    file_name: Optional[str] = None

class RecordsetDraftFileAdd(BaseModel):
    files: list[RecordsetDraftFileItem]

class RecordsetDraftFileRemove(BaseModel):
    # Membership ids, not file_ids -- removing one named copy must not remove
    # the other copies of the same content in the draft.
    recordset_draft_file_ids: list[int]

class RecordsetReleaseInsert(BaseModel):
    # All optional: release_number auto-assigns to the next unused number for
    # the recordset and release_date defaults to now(), matching
    # create_dataset_release. Supply either to override.
    release_number: Optional[int] = None
    release_date: Optional[datetime] = None
    release_notes: Optional[str] = None
    release_doi: Optional[str] = None

class DatasetReleaseTransferUpdate(BaseModel):
    transfer_name: Optional[str] = None
    transfer_mode_id: Optional[int] = None
    transfer_status: Optional[str] = None
    transfer_notes: Optional[str] = None

class TransferIdcUpdate(BaseModel):
    base_gcs_url: Optional[str] = None
    published: Optional[bool] = None
    public: Optional[bool] = None

class TransferGcUpdate(BaseModel):
    published: Optional[bool] = None
    public: Optional[bool] = None

class TransferAsperaUpdate(BaseModel):
    published: Optional[bool] = None
    public: Optional[bool] = None
    faspex_url: Optional[str] = None

class TransferNbiaUpdate(BaseModel):
    collection: Optional[str] = None
    site: Optional[str] = None
    published: Optional[bool] = None
    public: Optional[bool] = None

class TransferWpUpdate(BaseModel):
    wp_media_file_id: Optional[int] = None
    published: Optional[bool] = None
    public: Optional[bool] = None

class TransferReleaseRecordsetRequest(BaseModel):
    recordset_release_ids: list[int]

class FavoriteInsert(BaseModel):
    object_type: str
    object_id: int

# --- Response Models ---

class Meta(BaseModel):
    count: int

class DatasetType(BaseModel):
    dataset_type_id: int
    dataset_type_name: str

# --- Responses ---

def item_response(data):
    return {"data": data}


def list_response(rows):
    return {"data": rows, "meta": {"count": len(rows)}}


def api_error(
        code: str,
        message: str,
        details: Optional[dict] = None,
        status_code: int = 400):

    raise HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def db_error(
    e: Exception,
    *,
    operation: str,
    context: Optional[dict] = None):

    details = {"exception": type(e).__name__, "message": str(e), **(context or {})}

    if isinstance(e, asyncpg.exceptions.UniqueViolationError):
        api_error("CONFLICT", "Unique constraint violation", details, 409)

    if isinstance(e, asyncpg.exceptions.ForeignKeyViolationError):
        api_error("VALIDATION_ERROR", "Invalid foreign key reference", details, 422)

    api_error("INTERNAL_ERROR", f"Error {operation}", details, 500)






# -----------------------------------------LOOKUP TABLES------------------------------------------------




@router.get("/lookups/dataset-types")
# List dataset types
async def get_dataset_types(db: Database = Depends()):

    query = """
        select dataset_type_id, dataset_type_name
        from dataset_type
    """

    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching dataset types")

    return list_response(records)

@router.get("/lookups/dataset-relation-types")
# List dataset relation types
async def get_dataset_relation_types(db: Database = Depends()):

    query = """
        select relation_type_id,
            forward_label || ' --> <-- ' || reverse_label as relation_type_label
        from dataset_relation_type;
    """

    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching dataset relation types")

    return list_response(records)

@router.get("/lookups/recordset-types")
# List recordset types
async def get_recordset_types(db: Database = Depends()):

    query = """
        select recordset_type_id, recordset_type_name
        from recordset_type
    """

    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching recordset types")

    return list_response(records)

@router.get("/lookups/transfer-modes")
# List transfer modes
async def get_transfer_modes(db: Database = Depends()):

    query = """
        select transfer_mode_id, transfer_mode_name
        from transfer_mode
    """

    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching transfer modes")

    return list_response(records)

@router.get("/lookups/licenses")
# List licenses
async def get_licenses(db: Database = Depends()):

    query = """
        select license_id, license_name, license_label, license_url, is_public_access
        from recordset_license
    """

    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching licenses")

    return list_response(records)

@router.get("/lookups/destinations")
# List destinations
async def get_destinations(db: Database = Depends()):
    query = """\
        select destination_id, destination_name, destination_abbr
        from transfer_destination;
        """
    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching destinations")

    return list_response(records)

@router.get("/lookups/users")
# List active users
async def get_users(db: Database = Depends()):
    query = """\
        select user_id, user_name, full_name
        from auth.users
        where not disabled
        order by user_name
        """
    try:
        records = await db.fetch(query)
    except Exception as e:
        db_error(e, operation="fetching users")

    return list_response(records)

# -----------------------------------------FAVORITES-----------------------------------------------

@router.get("/favorites")
# List favorites for the current user
async def get_favorites(current_user: User = logged_in_user, db: Database = Depends()):
    query = """\
        select
            f.favorite_id,
            f.object_type,
            f.object_id,
            f.when_created,
            case
                when f.object_type = 'dataset' then d.dataset_name
                when f.object_type = 'recordset' then r.recordset_name
            end as object_name,
            case
                when f.object_type = 'dataset' then d.when_updated
                when f.object_type = 'recordset' then r.when_updated
            end as when_updated,
            case
                when f.object_type = 'recordset' then pd.dataset_name
            end as parent_dataset_name
        from public.user_favorite f
        left join public.dataset d on f.object_type = 'dataset' and f.object_id = d.dataset_id
        left join public.recordset r on f.object_type = 'recordset' and f.object_id = r.recordset_id
        left join public.dataset pd on r.dataset_id = pd.dataset_id
        where f.user_id = $1
        order by when_updated desc nulls last
        """
    try:
        records = await db.fetch(query, [current_user.user_id])
    except Exception as e:
        db_error(e, operation="fetching favorites")
    return list_response(records)


@router.post("/favorites")
# Add a favorite for the current user
async def add_favorite(
    payload: FavoriteInsert,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    query = """\
        with inserted as (
            insert into public.user_favorite (user_id, object_type, object_id)
            values ($1, $2, $3)
            on conflict (user_id, object_type, object_id) do update
                set object_id = excluded.object_id
            returning favorite_id, object_type, object_id, when_created
        )
        select
            i.favorite_id,
            i.object_type,
            i.object_id,
            i.when_created,
            coalesce(d.dataset_name, r.recordset_name) as object_name
        from inserted i
        left join public.dataset d on i.object_type = 'dataset' and i.object_id = d.dataset_id
        left join public.recordset r on i.object_type = 'recordset' and i.object_id = r.recordset_id
        """
    try:
        record = await db.fetch_one(query, [current_user.user_id, payload.object_type, payload.object_id])
    except Exception as e:
        db_error(e, operation="adding favorite")
    return item_response(record)


@router.delete("/favorites/{object_type}/{object_id}")
# Remove a favorite for the current user
async def remove_favorite(
    object_type: str,
    object_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    query = """\
        delete from public.user_favorite
        where user_id = $1 and object_type = $2 and object_id = $3
        """
    try:
        await db.execute(query, [current_user.user_id, object_type, object_id])
    except Exception as e:
        db_error(e, operation="removing favorite")
    return {"data": None}


# -----------------------------------------DATASETS------------------------------------------------

@router.get("/datasets")
# List datasets
async def get_datasets(
    search: Optional[str] = Query(default=None),
    active_only: Optional[bool] = Query(default=None),
    dataset_type_id: Optional[int] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    where_clauses = []
    values = []
    idx = 1

    if search:
        where_clauses.append(
            f"""(
                d.dataset_name ilike ${idx}
                or d.dataset_doi ilike ${idx}
                or dt.dataset_type_name ilike ${idx}
            )"""
        )
        values.append(f"%{search}%")
        idx += 1

    if active_only is True:
        where_clauses.append("d.active = true")

    if dataset_type_id is not None:
        where_clauses.append(f"d.dataset_type_id = ${idx}")
        values.append(dataset_type_id)
        idx += 1

    where_sql = f"where {' and '.join(where_clauses)}" if where_clauses else ""

    list_q = f"""\
        select
            d.dataset_id,
            d.dataset_type_id,
            dt.dataset_type_name,
            d.dataset_name,
            d.dataset_doi,
            d.active,
            d.who_created,
            d.when_created,
            d.who_updated,
            d.when_updated
        from
            dataset d
            join dataset_type dt using (dataset_type_id)
        {where_sql}
        order by d.dataset_id desc
        {page_clause(page, limit)}
        """
    count_q = f"select count(*) as total from dataset d join dataset_type dt using (dataset_type_id) {where_sql}"

    try:
        rows = await db.fetch(list_q, values)
        total = (await db.fetch(count_q, values))[0]["total"]
    except Exception as e:
        db_error(e, operation="fetching datasets")

    return paged_response(rows, total, page, limit)


@router.post("/datasets")
# Create dataset
async def create_dataset(
    payload: DatasetInsert,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if payload.dataset_type_id <= 0 or not payload.dataset_name.strip() or not payload.dataset_doi.strip():
        api_error(
            "VALIDATION_ERROR",
            "Required dataset fields must be non-empty",
            {
                "required": [
                    "dataset_type_id",
                    "dataset_name",
                    "dataset_doi",
                ]
            },
            422,
        )

    query = """\
        with inserted as (
            insert into dataset (
                dataset_type_id,
                dataset_name,
                dataset_doi,
                active,
                when_created,
                when_updated,
                who_created,
                who_updated
            )
            values ($1, $2, $3, $4, now(), now(), $5, $5)
            returning
                dataset_id,
                dataset_type_id,
                dataset_name,
                dataset_doi,
                active,
                who_created,
                when_created,
                who_updated,
                when_updated
        )
        select
            i.dataset_id,
            i.dataset_type_id,
            dt.dataset_type_name,
            i.dataset_name,
            i.dataset_doi,
            i.active,
            i.who_created,
            i.when_created,
            i.who_updated,
            i.when_updated
        from inserted i
        join dataset_type dt using (dataset_type_id)
        """

    values = [
        payload.dataset_type_id,
        payload.dataset_name,
        payload.dataset_doi,
        payload.active,
        current_user.user_id,
    ]

    try:
        record = await db.fetch(query, values)
    except Exception as e:
        db_error(e, operation="creating dataset")

    return item_response(record[0])


@router.get("/datasets/{dataset_id}")
# Get dataset detail
async def get_dataset(dataset_id: int, db: Database = Depends()):
    query = """\
        select
            d.dataset_id,
            d.dataset_type_id,
            dt.dataset_type_name,
            d.dataset_name,
            d.dataset_doi,
            d.active,
            d.who_created,
            d.when_created,
            d.who_updated,
            d.when_updated
        from
            dataset d
            join dataset_type dt using (dataset_type_id)
        where
            d.dataset_id = $1
        """

    try:
        record = await db.fetch(query, [dataset_id])
    except Exception as e:
        db_error(e, operation="fetching dataset", context={"dataset_id": dataset_id})

    if not record:
        api_error("NOT_FOUND", "Dataset not found", {"dataset_id": dataset_id}, 404)
    return item_response(record[0])


@router.put("/datasets/{dataset_id}")
# Update dataset metadata
async def update_dataset(
    dataset_id: int,
    payload: DatasetUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updates = []
    values = []
    idx = 1

    def add_text_field(column_name: str, value: Optional[str]):
        nonlocal idx
        if value is None:
            return

        if not value.strip():
            api_error("VALIDATION_ERROR", f"{column_name} must be non-empty", {"field": column_name}, 422)

        updates.append(f"{column_name} = ${idx}")
        values.append(value)
        idx += 1

    if payload.dataset_type_id is not None:
        updates.append(f"dataset_type_id = ${idx}")
        values.append(payload.dataset_type_id)
        idx += 1

    add_text_field("dataset_name", payload.dataset_name)
    add_text_field("dataset_doi", payload.dataset_doi)

    if payload.active is not None:
        updates.append(f"active = ${idx}")
        values.append(payload.active)
        idx += 1

    if not updates:
        api_error("VALIDATION_ERROR", "No dataset fields were provided", {}, 422)

    updates.append("when_updated = now()")
    updates.append(f"who_updated = ${idx}")
    values.append(current_user.user_id)
    idx += 1

    dataset_id_placeholder = idx

    query = f"""\
        with updated as (
            update dataset
            set {', '.join(updates)}
            where dataset_id = ${dataset_id_placeholder}
            returning
                dataset_id,
                dataset_type_id,
                dataset_name,
                dataset_doi,
                active,
                who_created,
                when_created,
                who_updated,
                when_updated
        )
        select
            u.dataset_id,
            u.dataset_type_id,
            dt.dataset_type_name,
            u.dataset_name,
            u.dataset_doi,
            u.active,
            u.who_created,
            u.when_created,
            u.who_updated,
            u.when_updated
        from updated u
        join dataset_type dt using (dataset_type_id)
        """

    values.append(dataset_id)

    try:
        record = await db.fetch(query, values)
    except Exception as e:
        db_error(e, operation="updating dataset", context={"dataset_id": dataset_id})

    if not record:
        api_error("NOT_FOUND", "Dataset not found", {"dataset_id": dataset_id}, 404)

    return item_response(record[0])


@router.get("/datasets/{dataset_id}/recordsets")
# List recordsets by dataset
async def get_recordsets_for_dataset(
    dataset_id: int,
    active_only: Optional[bool] = Query(default=None),
    db: Database = Depends()):

    query = """\
        select
            rs.recordset_id,
            rs.recordset_doi,
            rs.recordset_type_id,
            rt.recordset_type_name,
            rs.recordset_name,
            rsl.license_id,
            rsl.license_name,
            rsl.license_label,
            rsl.license_url,
            rsl.is_public_access,
            rs.active
        from
            dataset
            join recordset rs using (dataset_id)
            join recordset_type rt using (recordset_type_id)
            join recordset_license rsl using (license_id)
        where
            dataset_id = $1
        """

    if active_only is True:
        query += "\n and rs.active"

    try:
        records = await db.fetch(query, [dataset_id])
    except Exception as e:
        db_error(e, operation="fetching recordsets for dataset", context={"dataset_id": dataset_id})

    return list_response(records)


# A dataset release lifecycle: draft (being assembled) -> released (final on our
# side) -> live (a destination has published it externally, so the next change
# needs a new version number rather than an in-place overwrite). Retracted is
# terminal and withdraws the version.
DATASET_RELEASE_STATUSES = ("draft", "released", "live", "retracted")

# "Latest release" means the highest release_number that has not been retracted.
# A draft still counts -- a release being assembled is the one you want to see.
# Used everywhere latest is resolved so the definition cannot drift; note that
# datasets/Detail.tsx resolves latest client-side and must match.
NOT_RETRACTED = "release_status <> 'retracted'"


def validate_release_status(value: Optional[str]):
    if value is not None and value not in DATASET_RELEASE_STATUSES:
        api_error(
            "VALIDATION_ERROR",
            f"release_status must be one of {', '.join(DATASET_RELEASE_STATUSES)}",
            {"field": "release_status", "value": value},
            422,
        )


# Recordsets with their current cycle position: open draft, QC rollup over that
# draft's reviews, latest frozen release, and whether that release is bundled
# into the dataset's latest release. One row per recordset.
DATASET_CYCLE_RECORDSETS_SQL = """\
    with rs as (
        select rs.recordset_id, rs.recordset_name, rt.recordset_type_name
        from recordset rs
        join recordset_type rt using (recordset_type_id)
        where rs.dataset_id = $1
    ),
    open_draft as (
        select distinct on (d.recordset_id)
            d.recordset_id,
            d.recordset_draft_id,
            d.draft_name,
            d.draft_status,
            (select count(*)::int
               from recordset_draft_file f
              where f.recordset_draft_id = d.recordset_draft_id) as file_count,
            exists (select 1 from recordset_draft_file f
                    join file fl on fl.file_id = f.file_id
                    where f.recordset_draft_id = d.recordset_draft_id
                      and fl.is_dicom_file) as has_dicom,
            exists (select 1 from recordset_draft_file f
                    join file fl on fl.file_id = f.file_id
                    where f.recordset_draft_id = d.recordset_draft_id
                      and coalesce(fl.is_dicom_file, false) = false) as has_non_dicom
        from recordset_draft d
        where d.recordset_id in (select recordset_id from rs)
          and d.draft_status not in ('published', 'deleted')
        order by d.recordset_id, d.recordset_draft_id desc
    ),
    latest_rel as (
        select distinct on (r.recordset_id)
            r.recordset_id,
            r.recordset_release_id,
            r.release_number,
            r.release_date
        from recordset_release r
        where r.recordset_id in (select recordset_id from rs)
        order by r.recordset_id, r.release_number desc
    ),
    qc_draft as (
        select distinct on (d.recordset_id)
            d.recordset_id,
            d.recordset_draft_id
        from recordset_draft d
        where d.recordset_id in (select recordset_id from rs)
          and d.draft_status <> 'deleted'
        order by d.recordset_id, d.recordset_draft_id desc
    ),
    qc as (
        select
            od.recordset_id,
            od.recordset_draft_id as qc_draft_id,
            count(*)::int as reviews_total,
            count(*) filter (where v.review_status = 'open')::int as reviews_open,
            count(*) filter (where v.review_status = 'stale')::int as reviews_stale,
            count(*) filter (where v.review_status = 'complete')::int as reviews_complete,
            coalesce(sum(s.total), 0)::int as series_total,
            coalesce(sum(s.pending), 0)::int as series_pending,
            coalesce(sum(s.approved), 0)::int as series_approved
        from qc_draft od
        join qc_review v on v.recordset_draft_id = od.recordset_draft_id
        left join (
            select qc_review_id,
                count(*) as total,
                count(*) filter (where qc_status = 'pending') as pending,
                count(*) filter (where qc_status = 'approved') as approved
            from qc_unit group by qc_review_id
        ) s on s.qc_review_id = v.qc_review_id
        where v.review_status <> 'cancelled'
        group by od.recordset_id, od.recordset_draft_id
    ),
    bundled as (
        -- Released only, so in_dataset_release keeps meaning "a finished
        -- version of this recordset is part of that release". A draft release
        -- sitting in the membership means the cycle is still working on it,
        -- which is a different question -- see worked_this_cycle.
        select drr.recordset_release_id
        from dataset_release_recordset drr
        join recordset_release rr using (recordset_release_id)
        where drr.dataset_release_id = $2
          and rr.release_status = 'released'
    ),
    last_bundled as (
        -- Highest dataset release that *any* of this recordset's releases
        -- was ever bundled into -- distinct from in_dataset_release,
        -- which only checks the release this rollup describes. A
        -- recordset can sit at its own v3 while the dataset cuts newer
        -- releases around it (carry-forward), so this can be ahead of or
        -- behind the recordset's own latest_release.
        select rr.recordset_id, max(dr.release_number) as last_bundled_release_number
        from recordset_release rr
        join dataset_release_recordset drr on drr.recordset_release_id = rr.recordset_release_id
        join dataset_release dr on dr.dataset_release_id = drr.dataset_release_id
        where rr.recordset_id in (select recordset_id from rs)
          and rr.release_status = 'released'
        group by rr.recordset_id
    ),
    dest as (
        select
            rd.recordset_id,
            array_agg(rd.destination_id order by td.destination_abbr) as destination_ids,
            array_agg(td.destination_abbr order by td.destination_abbr) as destination_abbrs,
            array_agg(rd.default_display order by td.destination_abbr) as destination_defaults
        from recordset_destination rd
        join transfer_destination td using (destination_id)
        where rd.recordset_id in (select recordset_id from rs)
        group by rd.recordset_id
    ),
    wp_download as (
        select posda_object_id as recordset_id, wp_object_id, wp_edit_url
        from wp_object_map
        where posda_object_type = 'recordset' and wp_object_type = 'download'
    )
    select
        rs.recordset_id,
        rs.recordset_name,
        rs.recordset_type_name,
        od.recordset_draft_id,
        od.draft_name,
        od.draft_status,
        od.file_count,
        od.has_dicom,
        od.has_non_dicom,
        lr.recordset_release_id,
        lr.release_number,
        lr.release_date,
        q.qc_draft_id,
        coalesce(q.reviews_total, 0) as reviews_total,
        coalesce(q.reviews_open, 0) as reviews_open,
        coalesce(q.reviews_stale, 0) as reviews_stale,
        coalesce(q.reviews_complete, 0) as reviews_complete,
        coalesce(q.series_total, 0) as series_total,
        coalesce(q.series_pending, 0) as series_pending,
        coalesce(q.series_approved, 0) as series_approved,
        (lr.recordset_release_id is not null
         and lr.recordset_release_id in (select recordset_release_id from bundled))
            as in_dataset_release,
        lb.last_bundled_release_number,
        dest.destination_ids,
        dest.destination_abbrs,
        dest.destination_defaults,
        (wp_download.recordset_id is not null) as wp_linked,
        wp_download.wp_edit_url,
        wp_download.wp_object_id as wp_download_object_id
    from rs
    left join open_draft od using (recordset_id)
    left join latest_rel lr using (recordset_id)
    left join qc q using (recordset_id)
    left join last_bundled lb using (recordset_id)
    left join dest using (recordset_id)
    left join wp_download using (recordset_id)
    order by rs.recordset_id;
    """


def build_cycle_recordset(row):
    """Nest one flat cycle row into the recordset shape the UI consumes."""
    return {
        "recordset_id": row["recordset_id"],
        "recordset_name": row["recordset_name"],
        "recordset_type_name": row["recordset_type_name"],
        "open_draft": {
            "recordset_draft_id": row["recordset_draft_id"],
            "draft_name": row["draft_name"],
            "draft_status": row["draft_status"],
            "file_count": row["file_count"],
            "has_dicom": row["has_dicom"],
            "has_non_dicom": row["has_non_dicom"],
        } if row["recordset_draft_id"] is not None else None,
        # The draft the QC rollup was computed from -- the open draft while one
        # exists, otherwise the published draft it became. Lets a frozen
        # recordset's reviews stay reachable after open_draft goes null.
        "qc_draft_id": row["qc_draft_id"],
        "qc": {
            "reviews_total": row["reviews_total"],
            "open": row["reviews_open"],
            "stale": row["reviews_stale"],
            "complete": row["reviews_complete"],
            "series_total": row["series_total"],
            "series_pending": row["series_pending"],
            "series_approved": row["series_approved"],
        },
        "latest_release": {
            "recordset_release_id": row["recordset_release_id"],
            "release_number": row["release_number"],
            "release_date": row["release_date"],
        } if row["recordset_release_id"] is not None else None,
        "in_dataset_release": row["in_dataset_release"],
        "last_bundled_dataset_release_number": row["last_bundled_release_number"],
        "destinations": [
            {"destination_id": dest_id, "destination_abbr": abbr, "default_display": is_default}
            for dest_id, abbr, is_default in zip(
                row["destination_ids"] or [],
                row["destination_abbrs"] or [],
                row["destination_defaults"] or [],
            )
        ],
        "wp_linked": row["wp_linked"],
        "wp_edit_url": row["wp_edit_url"],
        "wp_download_object_id": row["wp_download_object_id"],
    }


async def count_orphaned_wp_downloads(wp_object_type: str, wp_object_id: int, attached_ids: set) -> int:
    """Downloads listed on the dataset's WP page that aren't the current
    download for any recordset here -- left behind by unlinking/relinking a
    recordset's download, or added directly in WordPress. Mirrors the check
    the Setup stage used to run client-side, moved server-side so it can gate
    setup completion consistently everywhere the cycle payload is read.
    Best-effort: a WordPress hiccup shouldn't fail the whole cycle page, so
    any error here just reports zero orphans rather than raising."""
    endpoint_key = "Collection" if wp_object_type == "collection" else "Analysis Result"
    downloads_field = "collection_downloads" if wp_object_type == "collection" else "result_downloads"
    try:
        item = await wp_get(f"{wp_url(endpoint_key)}/{wp_object_id}")
        if item is None:
            return 0
        listed_ids = item.get(downloads_field) or []
        orphaned_ids = [i for i in listed_ids if i not in attached_ids]
        if not orphaned_ids:
            return 0
        statuses = await asyncio.gather(
            *(wp_get(f"{wp_url('Download')}/{i}") for i in orphaned_ids),
            return_exceptions=True,
        )
        return sum(
            1 for s in statuses
            if isinstance(s, dict) and s.get("status") != "trash"
        )
    except Exception:
        return 0


@router.get("/datasets/{dataset_id}/cycle")
# Release-cycle rollup for a dataset: per-recordset pipeline position (draft ->
# QC -> frozen), one dataset release those releases fan into, and its transfers.
# Read-only; drives the cycle workspace and derived dashboard tasks.
#
# `release_id` pins the rollup to a specific release; without it the latest is
# used. Pinning is what keeps a shipping release reachable after the next cycle
# starts -- otherwise its transfers become invisible the moment a newer draft
# release exists. `latest_dataset_release_id` is always returned so the caller
# can tell whether it is looking at the current cycle.
async def get_dataset_cycle(
    dataset_id: int,
    release_id: Optional[int] = Query(default=None),
    db: Database = Depends()):
    dataset_q = """\
        select d.dataset_id, d.dataset_name, dt.dataset_type_name
        from dataset d
        join dataset_type dt using (dataset_type_id)
        where d.dataset_id = $1;
        """

    release_q = f"""\
        select dr.dataset_release_id, dr.release_number, dr.release_date,
               dr.release_doi, dr.release_status, dr.when_created
        from dataset_release dr
        where dr.dataset_id = $1
          and dr.{NOT_RETRACTED}
        order by dr.release_number desc
        limit 1;
        """

    # No NOT_RETRACTED filter here: asking for a release by id is explicit, and
    # a retracted release still has history worth looking at. The dataset_id
    # condition keeps one dataset's release from being read through another.
    pinned_release_q = """\
        select dr.dataset_release_id, dr.release_number, dr.release_date,
               dr.release_doi, dr.release_status, dr.when_created
        from dataset_release dr
        where dr.dataset_id = $1 and dr.dataset_release_id = $2;
        """

    transfers_q = """\
        select
            drt.dataset_release_transfer_id,
            drt.destination_id,
            td.destination_name,
            td.destination_abbr,
            drt.transfer_name,
            drt.transfer_status
        from dataset_release_transfer drt
        join transfer_destination td using (destination_id)
        where drt.dataset_release_id = $1
        order by td.destination_name;
        """

    # A dataset can only ever have one wp_object_map row (unique constraint on
    # posda_object_type + posda_object_id), so existence alone tells us it's
    # linked. Selecting the full row (not just `1`) lets the orphan check below
    # know which WP object to read the download list from.
    wp_collection_q = """\
        select wp_object_type, wp_object_id from wp_object_map
        where posda_object_type = 'dataset' and posda_object_id = $1
        limit 1;
        """

    try:
        dataset_rows = await db.fetch(dataset_q, [dataset_id])
    except Exception as e:
        db_error(e, operation="fetching dataset cycle", context={"dataset_id": dataset_id})

    if not dataset_rows:
        api_error("NOT_FOUND", "Dataset not found", {"dataset_id": dataset_id}, 404)

    try:
        release_rows = await db.fetch(release_q, [dataset_id])
        latest_release = release_rows[0] if release_rows else None
        latest_release_id = latest_release["dataset_release_id"] if latest_release else None

        if release_id is None:
            release = latest_release
        else:
            pinned_rows = await db.fetch(pinned_release_q, [dataset_id, release_id])
            if not pinned_rows:
                api_error(
                    "NOT_FOUND",
                    "Release not found for this dataset",
                    {"dataset_id": dataset_id, "release_id": release_id},
                    404,
                )
            release = pinned_rows[0]

        current_release_id = release["dataset_release_id"] if release else None

        recordset_rows = await db.fetch(
            DATASET_CYCLE_RECORDSETS_SQL, [dataset_id, current_release_id]
        )

        transfer_rows = (
            await db.fetch(transfers_q, [current_release_id]) if current_release_id else []
        )

        wp_collection_rows = await db.fetch(wp_collection_q, [dataset_id])
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="fetching dataset cycle", context={"dataset_id": dataset_id})

    dataset = dataset_rows[0]

    orphaned_download_count = 0
    if wp_collection_rows:
        attached_ids = {
            r["wp_download_object_id"] for r in recordset_rows
            if r["wp_download_object_id"] is not None
        }
        orphaned_download_count = await count_orphaned_wp_downloads(
            wp_collection_rows[0]["wp_object_type"],
            wp_collection_rows[0]["wp_object_id"],
            attached_ids,
        )

    return item_response({
        "dataset_id": dataset["dataset_id"],
        "dataset_name": dataset["dataset_name"],
        "dataset_type_name": dataset["dataset_type_name"],
        "recordsets": [build_cycle_recordset(r) for r in recordset_rows],
        "dataset_wp_linked": bool(wp_collection_rows),
        "orphaned_download_count": orphaned_download_count,
        # The release this rollup describes -- pinned when release_id was given,
        # otherwise the latest. Compare against latest_dataset_release_id to see
        # whether this is the current cycle or an older one still being viewed.
        "latest_dataset_release_id": latest_release_id,
        "dataset_release": {
            "dataset_release_id": release["dataset_release_id"],
            "release_number": release["release_number"],
            "release_date": release["release_date"],
            "release_doi": release["release_doi"],
            "release_status": release["release_status"],
            # When the cycle started. release_date is null while draft, so this
            # is the only marker of "work done during this cycle".
            "when_created": release["when_created"],
            "transfers": [dict(t) for t in transfer_rows],
        } if release else None,
    })


@router.get("/datasets/{dataset_id}/releases")
# List dataset releases by dataset
async def get_releases_for_dataset(
    dataset_id: int,
    latest_only: Optional[bool] = Query(default=None),
    db: Database = Depends()):

    query = f"""\
        select
            dr.dataset_release_id,
            d.dataset_id,
            dr.release_number,
            dr.release_date,
            dr.release_notes,
            dr.release_doi,
            dr.release_status
        from
            dataset d
            join dataset_release dr using (dataset_id)
        where
            d.dataset_id = $1
        """

    # Latest excludes retracted versions; the unfiltered list keeps them so the
    # history stays auditable.
    if latest_only is True:
        query += f"\n and dr.{NOT_RETRACTED}"

    query += "\norder by dr.release_number desc"

    if latest_only is True:
        query += "\nlimit 1"

    try:
        records = await db.fetch(query, [dataset_id])
    except Exception as e:
        db_error(e, operation="fetching dataset releases", context={"dataset_id": dataset_id})

    return list_response(records)


@router.post("/datasets/{dataset_id}/releases")
# Create a new dataset release
async def create_dataset_release(
    dataset_id: int,
    payload: DatasetReleaseInsert,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    validate_release_status(payload.release_status)
    release_status = payload.release_status or "draft"

    open_draft_q = """
        select dataset_release_id from dataset_release
        where dataset_id = $1 and release_status = 'draft'
        limit 1
    """

    # release_number auto-assigns to the next unused number for this dataset
    # when omitted. release_date stays null while draft; if a release is
    # created directly as 'released' with no explicit date, stamp it now
    # rather than leaving a released release with no date.
    query = """\
        insert into dataset_release (dataset_id, release_number, release_date, release_notes, release_doi, release_status, when_created, who_created, when_updated, who_updated)
        values (
            $1,
            coalesce($2::int, (select coalesce(max(release_number), 0) + 1 from dataset_release where dataset_id = $1)),
            coalesce($3::timestamptz, case when $6 = 'released' then now() end),
            $4, $5, $6, now(), $7, now(), $7
        )
        returning dataset_release_id, dataset_id, release_number, release_date, release_notes, release_doi, release_status
    """
    values = [
        dataset_id,
        payload.release_number,
        payload.release_date,
        payload.release_notes,
        payload.release_doi,
        release_status,
        current_user.user_id,
    ]

    try:
        async with db.transaction() as conn:
            # One draft dataset_release per dataset -- the policy the cycle
            # view assumes ("Start Next Cycle" is only offered when none
            # exists, but the guard belongs here so it holds regardless of
            # caller, e.g. the standalone releases/Create.tsx form).
            if release_status == "draft":
                existing = await conn.fetch(open_draft_q, dataset_id)
                if existing:
                    api_error(
                        "CONFLICT",
                        f"Dataset {dataset_id} already has a draft release",
                        {
                            "dataset_id": dataset_id,
                            "dataset_release_id": existing[0]["dataset_release_id"],
                        },
                        409,
                    )

            record = await conn.fetch(query, *values)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="creating dataset release", context={"dataset_id": dataset_id})

    if not record:
        api_error("NOT_FOUND", "Dataset not found", {"dataset_id": dataset_id}, 404)

    return item_response(record[0])

# -----------------------------------------DATASET RELEASES------------------------------------------------

@router.get("/datasets/releases/{release_id}")
# Get dataset release detail
async def get_dataset_release(release_id: int, db: Database = Depends()):
    query = """\
        select
            dr.dataset_release_id,
            dr.dataset_id,
            dr.release_number,
            dr.release_date,
            dr.release_notes,
            dr.release_doi,
            dr.release_status,
            dr.when_created,
            dr.who_created,
            dr.when_updated,
            dr.who_updated
        from dataset_release dr
        where dr.dataset_release_id = $1
        """
    try:
        record = await db.fetch(query, [release_id])
    except Exception as e:
        db_error(e, operation="fetching dataset release", context={"release_id": release_id})

    if not record:
        api_error("NOT_FOUND", "Dataset release not found", {"release_id": release_id}, 404)

    return item_response(record[0])


@router.put("/datasets/releases/{release_id}")
# Update dataset release
async def update_dataset_release(
    release_id: int,
    payload: DatasetReleaseUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updates = []
    values = []
    idx = 1

    if payload.dataset_id is not None:
        updates.append(f"dataset_id = ${idx}")
        values.append(payload.dataset_id)
        idx += 1

    if payload.release_number is not None:
        updates.append(f"release_number = ${idx}")
        values.append(payload.release_number)
        idx += 1

    if payload.release_date is not None:
        updates.append(f"release_date = ${idx}")
        values.append(payload.release_date)
        idx += 1

    if payload.release_notes is not None:
        updates.append(f"release_notes = ${idx}")
        values.append(payload.release_notes)
        idx += 1

    if payload.release_doi is not None:
        updates.append(f"release_doi = ${idx}")
        values.append(payload.release_doi)
        idx += 1

    if payload.release_status is not None:
        validate_release_status(payload.release_status)
        updates.append(f"release_status = ${idx}")
        values.append(payload.release_status)
        idx += 1

        # release_date is null while draft; publishing (-> released) stamps it
        # now unless the caller already set an explicit date above.
        if payload.release_status == "released" and payload.release_date is None:
            updates.append("release_date = coalesce(release_date, now())")

    if not updates:
        api_error("VALIDATION_ERROR", "No dataset release fields were provided", {}, 422)

    updates.append("when_updated = now()")
    updates.append(f"who_updated = ${idx}")
    values.append(current_user.user_id)
    idx += 1

    release_id_placeholder = idx

    query = f"""
        update dataset_release
        set {', '.join(updates)}
        where dataset_release_id = ${release_id_placeholder}
        returning
            dataset_release_id,
            dataset_id,
            release_number,
            release_date,
            release_notes,
            release_doi,
            release_status,
            when_created,
            who_created,
            when_updated,
            who_updated
    """

    values.append(release_id)

    try:
        record = await db.fetch(query, values)
    except Exception as e:
        db_error(e, operation="updating dataset release", context={"release_id": release_id})

    if not record:
        api_error("NOT_FOUND", "Dataset release not found", {"release_id": release_id}, 404)

    return item_response(record[0])


@router.get("/datasets/releases/{release_id}/recordsets")
# List recordset releases in a dataset release, optionally filtered to those configured for a destination
async def get_recordsets_for_dataset_release(
    release_id: int,
    destination_id: Optional[int] = Query(default=None),
    db: Database = Depends()):

    if destination_id is not None:
        query = """\
            select
                rr.recordset_id,
                rr.recordset_release_id,
                rs.recordset_name,
                rr.release_number,
                rr.release_date
            from dataset_release dr
            join dataset_release_recordset drr using (dataset_release_id)
            join recordset_release rr using (recordset_release_id)
            join recordset rs using (recordset_id)
            join recordset_destination rd
                on rs.recordset_id = rd.recordset_id and rd.destination_id = $2
            where dr.dataset_release_id = $1
              and rr.release_status = 'released'
            """
        args = [release_id, destination_id]
    else:
        query = """\
            select
                rr.recordset_id,
                rr.recordset_release_id,
                rs.recordset_name,
                rr.release_number,
                rr.release_date
            from dataset_release dr
            join dataset_release_recordset drr using (dataset_release_id)
            join recordset_release rr using (recordset_release_id)
            join recordset rs using (recordset_id)
            where dr.dataset_release_id = $1
              and rr.release_status = 'released'
            """
        args = [release_id]

    try:
        records = await db.fetch(query, args)
    except Exception as e:
        db_error(e, operation="fetching recordset releases for dataset release", context={"release_id": release_id})

    return list_response(records)


@router.post("/datasets/releases/{release_id}/recordsets/add")
# Add recordset releases to a dataset release
async def add_recordset_release_to_dataset_release(
    release_id: int,
    payload: DatasetReleaseRecordsetRequest,
    db: Database = Depends()):

    # One version per recordset per dataset release. The PK is on
    # (dataset_release_id, recordset_release_id), so nothing at the storage
    # layer stops v1 and v2 of the same recordset both being bundled -- and the
    # Bundle stage's version picker is exactly a swap. So adding a release
    # first evicts any other release of the same recordset, making "include
    # this version" a single idempotent call.
    replace_query = """
            delete from dataset_release_recordset drr
            using recordset_release existing, recordset_release incoming
            where drr.dataset_release_id = $1
              and existing.recordset_release_id = drr.recordset_release_id
              and incoming.recordset_release_id = any($2::int[])
              and existing.recordset_id = incoming.recordset_id
              and drr.recordset_release_id <> incoming.recordset_release_id
            returning drr.recordset_release_id
        """

    insert_query = """
            insert into dataset_release_recordset
            (dataset_release_id, recordset_release_id)
            select $1, id from unnest($2::int[]) as id
            on conflict do nothing
            returning recordset_release_id
        """

    count_query = """
            select count(*) as current_count
            from dataset_release_recordset
            where dataset_release_id = $1
        """

    recordset_release_ids = payload.recordset_release_ids

    if not recordset_release_ids:
        api_error(
            "VALIDATION_ERROR",
            "No records to insert",
            {"recordset_release_ids": []},
            422,
        )

    try:
        # One transaction: a partial add used to be possible (the insert ran
        # per id outside any transaction), and a re-add raised a PK violation
        # that surfaced as a 500.
        async with db.transaction() as conn:
            replaced = await conn.fetch(replace_query, release_id, recordset_release_ids)
            added = await conn.fetch(insert_query, release_id, recordset_release_ids)
            count_record = await conn.fetch(count_query, release_id)
    except Exception as e:
        db_error(
            e,
            operation="adding recordset releases to dataset release",
            context={"release_id": release_id},
        )

    return item_response(
        {
            "dataset_release_id": release_id,
            "added_recordset_release_ids": [r["recordset_release_id"] for r in added],
            "replaced_recordset_release_ids": [r["recordset_release_id"] for r in replaced],
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


@router.post("/datasets/releases/{release_id}/recordsets/remove")
# Remove recordset releases from a dataset release
async def remove_recordset_release_from_dataset_release(
    release_id: int,
    payload: DatasetReleaseRecordsetRequest,
    db: Database = Depends()):

    delete_query = """
            delete from dataset_release_recordset
            where dataset_release_id = $1 and recordset_release_id = $2
            returning recordset_release_id
        """
    count_query = """
            select count(*) as current_count
            from dataset_release_recordset
            where dataset_release_id = $1
        """

    recordset_release_ids = payload.recordset_release_ids

    if not recordset_release_ids:
        api_error(
            "VALIDATION_ERROR",
            "No records to remove",
            {"recordset_release_ids": []},
            422,
        )

    removed_recordset_release_ids = []

    try:
        for recordset_release_id in recordset_release_ids:
            record = await db.fetch(delete_query, [release_id, recordset_release_id])
            if record:
                removed_recordset_release_ids.append(record[0]["recordset_release_id"])

        count_record = await db.fetch(count_query, [release_id])
    except Exception as e:
        db_error(
            e,
            operation="removing recordset releases from dataset release",
            context={"release_id": release_id},
        )

    return item_response(
        {
            "dataset_release_id": release_id,
            "removed_recordset_release_ids": removed_recordset_release_ids,
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


@router.get("/datasets/releases/{release_id}/transfers")
# List transfers for a dataset release
async def get_transfers_for_dataset_release(release_id: int, db: Database = Depends()):
    # A transfer's membership is snapshotted into transfer_recordset when it
    # is created, but what it *should* carry can move afterwards: a recordset
    # gains or loses this destination in Setup, or -- the case that matters
    # most -- Bundle's version picker swaps which recordset_release the
    # dataset release carries, leaving the transfer pointed at the superseded
    # release. Nothing surfaced that, so a stale transfer would ship the wrong
    # version to an external destination silently. Compared here rather than
    # making the UI fetch both sets per row.
    #
    # Counts alone are not enough -- one added plus one removed leaves the
    # count unchanged -- so the actual and expected id sets are compared.
    query = """\
        with actual as (
            select
                tr.dataset_release_transfer_id as tid,
                array_agg(distinct tr.recordset_release_id
                          order by tr.recordset_release_id) as ids
            from transfer_recordset tr
            join dataset_release_transfer drt using (dataset_release_transfer_id)
            where drt.dataset_release_id = $1
            group by 1
        ),
        expected as (
            select
                drt.dataset_release_transfer_id as tid,
                array_agg(distinct drr.recordset_release_id
                          order by drr.recordset_release_id) as ids
            from dataset_release_transfer drt
            join dataset_release_recordset drr
                on drr.dataset_release_id = drt.dataset_release_id
            join recordset_release rr
                on rr.recordset_release_id = drr.recordset_release_id
            join recordset_destination rd
                on rd.recordset_id = rr.recordset_id
               and rd.destination_id = drt.destination_id
            where drt.dataset_release_id = $1
              and rr.release_status = 'released'
            group by 1
        )
        select
            drt.dataset_release_transfer_id,
            drt.destination_id,
            td.destination_name,
            td.destination_abbr,
            drt.transfer_name,
            drt.transfer_mode_id,
            tm.transfer_mode_name,
            drt.transfer_status,
            drt.transfer_notes,
            coalesce(cardinality(a.ids), 0) as recordset_count,
            coalesce(cardinality(e.ids), 0) as expected_recordset_count,
            coalesce(a.ids, '{}'::int[])
                is distinct from coalesce(e.ids, '{}'::int[]) as membership_drifted
        from dataset_release_transfer drt
        join transfer_destination td using (destination_id)
        join transfer_mode tm using (transfer_mode_id)
        left join actual a   on a.tid = drt.dataset_release_transfer_id
        left join expected e on e.tid = drt.dataset_release_transfer_id
        where drt.dataset_release_id = $1;
        """
    try:
        records = await db.fetch(query, [release_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching dataset release transfers",
            context={"release_id": release_id},
        )

    return list_response(records)


@router.get("/datasets/releases/{release_id}/destinations")
# List suggested destinations for a dataset release (aggregated from recordset_destination configs)
async def get_destinations_for_dataset_release(release_id: int, db: Database = Depends()):
    query = """\
        select distinct on (td.destination_id)
            td.destination_id,
            td.destination_name,
            td.destination_abbr,
            rd.transfer_mode_id,
            tm.transfer_mode_name
        from dataset_release_recordset drr
        join recordset_release rr using (recordset_release_id)
        join recordset r using (recordset_id)
        join recordset_destination rd using (recordset_id)
        join transfer_destination td using (destination_id)
        join transfer_mode tm using (transfer_mode_id)
        where drr.dataset_release_id = $1
          and rr.release_status = 'released'
        order by td.destination_id, rd.default_display desc
        """
    try:
        records = await db.fetch(query, [release_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching destinations for dataset release",
            context={"release_id": release_id},
        )

    return list_response(records)


@router.post("/datasets/releases/{release_id}/transfers")
# Create transfer for a dataset release — atomically links all recordset releases in one transaction
async def create_transfer_for_dataset_release(
    release_id: int,
    payload: DatasetReleaseTransferInsert,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if payload.destination_id <= 0 or payload.transfer_mode_id <= 0 or not payload.transfer_name.strip():
        api_error(
            "VALIDATION_ERROR",
            "Required transfer fields must be non-empty",
            {"required": ["destination_id", "transfer_name", "transfer_mode_id"]},
            422,
        )

    # A draft release is still being composed -- its membership can change under
    # a transfer that has already snapshotted it. The cycle's Transfer stage
    # hides its controls while the release is a draft, but that was UI-only
    # (TECH_DEBT #5); enforce it here so the API cannot be used around it.
    release_row = await db.fetch_one(
        "select release_status from dataset_release where dataset_release_id = $1",
        [release_id],
    )
    if not release_row:
        api_error("NOT_FOUND", "Dataset release not found", {"release_id": release_id}, 404)
    if release_row["release_status"] == "draft":
        api_error(
            "VALIDATION_ERROR",
            "Cannot create a transfer for a draft release -- finalize it first",
            {"release_id": release_id, "release_status": "draft"},
            422,
        )

    insert_transfer_query = """\
        with inserted as (
            insert into dataset_release_transfer (
                dataset_release_id,
                destination_id,
                transfer_name,
                transfer_mode_id,
                transfer_status,
                transfer_notes,
                when_created,
                when_updated,
                who_created,
                who_updated
            )
            values ($1, $2, $3, $4, $5, $6, now(), now(), $7, $7)
            returning
                dataset_release_transfer_id,
                destination_id,
                transfer_name,
                transfer_mode_id,
                transfer_status,
                transfer_notes
        )
        select
            i.dataset_release_transfer_id,
            i.destination_id,
            td.destination_name,
            td.destination_abbr,
            i.transfer_name,
            i.transfer_mode_id,
            tm.transfer_mode_name,
            i.transfer_status,
            i.transfer_notes
        from inserted i
        join transfer_destination td using (destination_id)
        join transfer_mode tm using (transfer_mode_id)
        """

    # Released only. A dataset release's membership includes draft recordset
    # releases while the cycle is still assembling them, and shipping one would
    # upload files that are not final -- an upload that cannot be recalled.
    get_release_recordsets_query = """\
        select drr.recordset_release_id
        from dataset_release_recordset drr
        join recordset_release rr using (recordset_release_id)
        where drr.dataset_release_id = $1
          and rr.release_status = 'released'
        """

    insert_transfer_recordset_query = """\
        insert into transfer_recordset (dataset_release_transfer_id, recordset_release_id)
        values ($1, $2)
        on conflict do nothing
        """

    transfer_values = [
        release_id,
        payload.destination_id,
        payload.transfer_name,
        payload.transfer_mode_id,
        payload.transfer_status,
        payload.transfer_notes,
        current_user.user_id,
    ]

    record = []
    try:
        async with db.transaction() as conn:
            rows = await conn.fetch(insert_transfer_query, *transfer_values)
            record = rows
            transfer_id = rows[0]["dataset_release_transfer_id"]

            recordset_ids = payload.recordset_release_ids
            if not recordset_ids:
                rs_rows = await conn.fetch(get_release_recordsets_query, release_id)
                recordset_ids = [r["recordset_release_id"] for r in rs_rows]

            for rs_id in recordset_ids:
                await conn.execute(insert_transfer_recordset_query, transfer_id, rs_id)

    except HTTPException:
        raise
    except Exception as e:
        db_error(
            e,
            operation="creating dataset release transfer",
            context={"release_id": release_id, "destination_id": payload.destination_id},
        )

    return item_response(record[0])


# -----------------------------------------RECORDSETS------------------------------------------------

@router.get("/recordsets")
# List recordsets
async def get_recordsets(
    dataset_id: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None),
    active_only: Optional[bool] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    where_clauses = []
    values = []
    idx = 1

    if dataset_id is not None:
        where_clauses.append(f"r.dataset_id = ${idx}")
        values.append(dataset_id)
        idx += 1

    if search:
        where_clauses.append(
            f"""(
                r.recordset_name ilike ${idx}
                or r.recordset_doi ilike ${idx}
                or rt.recordset_type_name ilike ${idx}
            )"""
        )
        values.append(f"%{search}%")
        idx += 1

    if active_only is True:
        where_clauses.append("r.active = true")

    where_sql = f"where {' and '.join(where_clauses)}" if where_clauses else ""

    list_q = f"""\
        select
            r.recordset_id,
            r.recordset_doi,
            r.dataset_id,
            d.dataset_name,
            d.dataset_type_id,
            dt.dataset_type_name,
            r.license_id,
            rsl.license_name,
            rsl.license_label,
            rsl.license_url,
            rsl.is_public_access,
            r.recordset_type_id,
            rt.recordset_type_name,
            r.recordset_name,
            r.active,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated
        from
            recordset r
            join recordset_type rt using (recordset_type_id)
            join recordset_license rsl using (license_id)
            join dataset d using (dataset_id)
            join dataset_type dt using (dataset_type_id)
        {where_sql}
        order by r.recordset_id desc
        {page_clause(page, limit)}
        """
    count_q = f"""\
        select count(*) as total
        from recordset r
            join recordset_type rt using (recordset_type_id)
            join dataset d using (dataset_id)
        {where_sql}
        """

    try:
        records = await db.fetch(list_q, values)
        total = (await db.fetch(count_q, values))[0]["total"]
    except Exception as e:
        db_error(e, operation="fetching recordsets")

    return paged_response(records, total, page, limit)


@router.post("/recordsets")
# Create recordset
async def create_recordset(
    payload: RecordsetCreate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if (
        not payload.recordset_name.strip()
        or payload.recordset_type_id <= 0
        or payload.dataset_id <= 0
        or payload.license_id <= 0
    ):
        api_error(
            "VALIDATION_ERROR",
            "Required recordset fields must be non-empty",
            {
                "required": [
                    "recordset_type_id",
                    "recordset_name",
                    "dataset_id",
                    "license_id",
                ]
            },
            422,
        )

    query = """\
        insert into recordset (
            recordset_doi,
            dataset_id,
            license_id,
            recordset_type_id,
            recordset_name,
            active,
            when_created,
            when_updated,
            who_created,
            who_updated
        )
        values ($1, $2, $3, $4, $5, $6, now(), now(), $7, $7)
        returning
            recordset_id,
            recordset_doi,
            dataset_id,
            license_id,
            recordset_type_id,
            recordset_name,
            active,
            when_created,
            when_updated
        """

    values = [
        payload.recordset_doi,
        payload.dataset_id,
        payload.license_id,
        payload.recordset_type_id,
        payload.recordset_name,
        payload.active,
        current_user.user_id,
    ]

    try:
        record = await db.fetch(query, values)
    except Exception as e:
        db_error(
            e,
            operation="creating recordset",
        )

    return item_response(record[0])


@router.get("/recordsets/{recordset_id}")
# Get recordset detail
async def get_recordset(recordset_id: int, db: Database = Depends()):
    query = """\
        select
            r.recordset_id,
            r.recordset_doi,
            r.dataset_id,
            d.dataset_name,
            d.dataset_type_id,
            dt.dataset_type_name,
            r.recordset_type_id,
            rt.recordset_type_name,
            r.recordset_name,
            r.active,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated,
            rl.license_id,
            rl.license_name,
            rl.license_label,
            rl.license_url,
            rl.is_public_access
        from
            recordset r
            join recordset_type rt using (recordset_type_id)
            join recordset_license rl using (license_id)
            join dataset d using (dataset_id)
            join dataset_type dt using (dataset_type_id)
        where
            r.recordset_id = $1;
        """
    try:
        record = await db.fetch(query, [recordset_id])
    except Exception as e:
        db_error(e, operation="fetching recordset", context={"recordset_id": recordset_id})

    if not record:
        api_error("NOT_FOUND", "Recordset not found", {"recordset_id": recordset_id}, 404)

    return item_response(record[0])


@router.put("/recordsets/{recordset_id}")
# Update recordset
async def update_recordset(
    recordset_id: int,
    payload: RecordsetUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updates = []
    values = []
    idx = 1

    def add_text_field(column_name: str, value: Optional[str]):
        nonlocal idx
        if value is None:
            return

        if not value.strip():
            api_error("VALIDATION_ERROR", f"{column_name} must be non-empty", {"field": column_name}, 422)

        updates.append(f"{column_name} = ${idx}")
        values.append(value)
        idx += 1

    # recordset_doi is nullable and optional, so clearing it is a real edit --
    # which add_text_field cannot express: None means "not provided" and is
    # skipped, and "" is rejected as empty, so the DOI could never be removed
    # once set. model_fields_set separates the two cases: absent from the body
    # means leave it alone, present-but-blank means clear it.
    if "recordset_doi" in payload.model_fields_set:
        updates.append(f"recordset_doi = ${idx}")
        values.append((payload.recordset_doi or "").strip() or None)
        idx += 1

    add_text_field("recordset_name", payload.recordset_name)

    if payload.recordset_type_id is not None:
        updates.append(f"recordset_type_id = ${idx}")
        values.append(payload.recordset_type_id)
        idx += 1

    if payload.dataset_id is not None:
        updates.append(f"dataset_id = ${idx}")
        values.append(payload.dataset_id)
        idx += 1

    if payload.license_id is not None:
        updates.append(f"license_id = ${idx}")
        values.append(payload.license_id)
        idx += 1

    if payload.active is not None:
        updates.append(f"active = ${idx}")
        values.append(payload.active)
        idx += 1

    if not updates:
        api_error("VALIDATION_ERROR", "No recordset fields were provided", {}, 422)

    updates.append("when_updated = now()")
    updates.append(f"who_updated = ${idx}")
    values.append(current_user.user_id)
    idx += 1

    recordset_id_placeholder = idx
    values.append(recordset_id)

    query = f"""\
        with updated as (
            update recordset
            set {', '.join(updates)}
            where recordset_id = ${recordset_id_placeholder}
            returning
                recordset_id,
                recordset_doi,
                dataset_id,
                license_id,
                recordset_type_id,
                recordset_name,
                active,
                when_created,
                who_created,
                when_updated,
                who_updated
        )
        select
            u.recordset_id,
            u.recordset_doi,
            u.dataset_id,
            d.dataset_name,
            d.dataset_type_id,
            dt.dataset_type_name,
            u.recordset_type_id,
            rt.recordset_type_name,
            u.recordset_name,
            u.active,
            u.when_created,
            u.who_created,
            u.when_updated,
            u.who_updated,
            rl.license_name,
            rl.license_id,
            rl.license_label,
            rl.license_url,
            rl.is_public_access
        from updated u
        join recordset_type rt using (recordset_type_id)
        join recordset_license rl using (license_id)
        join dataset d using (dataset_id)
        join dataset_type dt using (dataset_type_id)
        """

    try:
        record = await db.fetch(query, values)
    except Exception as e:
        db_error(
            e,
            operation="updating recordset",
            context={"recordset_id": recordset_id},
        )

    if not record:
        api_error("NOT_FOUND", "Recordset not found", {"recordset_id": recordset_id}, 404)

    return item_response(record[0])


@router.get("/recordsets/{recordset_id}/drafts")
# List draft releases for a recordset
async def get_recordset_drafts(recordset_id: int, db: Database = Depends()):
    query = """\
        select
            r.recordset_draft_id,
            r.recordset_id,
            r.cloned_from_release_id,
            r.draft_name,
            r.draft_status,
            r.draft_notes,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated,
            count(rdf.file_id)::int as file_count
        from
            recordset_draft r
            left join recordset_draft_file rdf using (recordset_draft_id)
        where
            r.recordset_id = $1
        and
            r.draft_status <> 'deleted'
        group by
            r.recordset_draft_id,
            r.recordset_id,
            r.cloned_from_release_id,
            r.draft_name,
            r.draft_status,
            r.draft_notes,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated
        order by
            r.recordset_draft_id;
        """
    try:
        records = await db.fetch(query, [recordset_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset drafts",
            context={"recordset_id": recordset_id},
        )

    return list_response(records)


@router.get("/recordsets/{recordset_id}/releases")
# List immutable releases for a recordset
async def get_recordset_releases(recordset_id: int, db: Database = Depends()):
    query = """\
        select
            r.recordset_release_id,
            r.recordset_id,
            r.release_number,
            r.release_date,
            r.release_notes,
            r.release_doi,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated,
            count(rrf.file_id)::int as file_count
        from
            recordset_release r
            left join recordset_release_file rrf using (recordset_release_id)
        where
            r.recordset_id = $1
        group by
            r.recordset_release_id,
            r.recordset_id,
            r.release_number,
            r.release_date,
            r.release_notes,
            r.release_doi,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated
        order by
            r.release_number;
        """
    try:
        records = await db.fetch(query, [recordset_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset releases",
            context={"recordset_id": recordset_id},
        )

    return list_response(records)


@router.get("/recordsets/{recordset_id}/destinations")
# List destinations for a recordset
async def get_recordset_destinations(recordset_id: int, db: Database = Depends()):
    query = """\
        select
            rd.destination_id,
            td.destination_name,
            td.destination_abbr,
            rd.default_display,
            rd.transfer_mode_id,
            tm.transfer_mode_name
        from recordset_destination rd
            join transfer_destination td using (destination_id)
            join transfer_mode tm using (transfer_mode_id)
        where
            rd.recordset_id = $1;
        """
    try:
        records = await db.fetch(query, [recordset_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset destinations",
            context={"recordset_id": recordset_id},
        )
    return list_response(records)


# -----------------------------------------RECORDSET DESTINATIONS------------------------------------------------

@router.get("/recordsets/{recordset_id}/destinations/{destination_id}")
# Get a destination specific configuration for a recordset
async def get_recordset_destination(recordset_id: int, destination_id: int, db: Database = Depends()):
    query = """\
        select
            rd.destination_id,
            td.destination_name,
            td.destination_abbr,
            rd.default_display,
            rd.transfer_mode_id,
            tm.transfer_mode_name
        from recordset_destination rd
            join transfer_destination td using (destination_id)
            join transfer_mode tm using (transfer_mode_id)
        where
            rd.recordset_id = $1 and rd.destination_id = $2;
        """
    try:
        records = await db.fetch(query, [recordset_id, destination_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching a recordset destination",
            context={"recordset_id": recordset_id, "destination_id": destination_id},
        )
    return list_response(records)


@router.put("/recordsets/{recordset_id}/destinations/{destination_id}")
# Create or update a destination configuration for a recordset
async def update_recordset_destination(
    recordset_id: int,
    destination_id: int,
    payload: DestinationUpdate,
    db: Database = Depends()
):
    updates = []
    update_values = []
    idx = 3

    if payload.default_display is not None:
        updates.append(f"default_display = ${idx}")
        update_values.append(payload.default_display)
        idx += 1

    if payload.default_transfer_mode_id is not None:
        updates.append(f"transfer_mode_id = ${idx}")
        update_values.append(payload.default_transfer_mode_id)
        idx += 1

    if not updates:
        api_error("VALIDATION_ERROR", "No destination fields were provided", {}, 422)

    exists_query = """\
        select 1
        from recordset_destination
        where recordset_id = $1 and destination_id = $2
        limit 1
    """

    has_any_query = """\
        select 1
        from recordset_destination
        where recordset_id = $1
        limit 1
    """

    clear_default_query = """\
        update recordset_destination
        set default_display = false
        where recordset_id = $1
          and destination_id <> $2
          and default_display = true
    """

    insert_query = """\
        insert into recordset_destination (
            recordset_id,
            destination_id,
            default_display,
            transfer_mode_id
        )
        values ($1, $2, $3, $4)
        returning *
    """

    record = []

    try:
        async with db.transaction() as conn:
            existing = await conn.fetch(exists_query, recordset_id, destination_id)

            if existing:
                if payload.default_display is True:
                    await conn.execute(clear_default_query, recordset_id, destination_id)

                update_query = f"""\
                    update recordset_destination
                    set {', '.join(updates)}
                    where recordset_id = $1 and destination_id = $2
                    returning *
                """

                record = await conn.fetch(
                    update_query,
                    recordset_id,
                    destination_id,
                    *update_values,
                )
            else:
                if payload.default_display is None or payload.default_transfer_mode_id is None:
                    api_error(
                        "VALIDATION_ERROR",
                        "default_display and default_transfer_mode_id are required for insert",
                        {
                            "required": ["default_display", "default_transfer_mode_id"],
                            "recordset_id": recordset_id,
                            "destination_id": destination_id,
                        },
                        422,
                    )

                # A recordset's first destination is always its default --
                # never leave one with destinations but none marked default.
                has_any = await conn.fetch(has_any_query, recordset_id)
                effective_default = True if not has_any else payload.default_display

                if effective_default is True:
                    await conn.execute(clear_default_query, recordset_id, destination_id)

                record = await conn.fetch(
                    insert_query,
                    recordset_id,
                    destination_id,
                    effective_default,
                    payload.default_transfer_mode_id,
                )
    except HTTPException:
        raise
    except Exception as e:
        db_error(
            e,
            operation="upserting recordset destination",
            context={"recordset_id": recordset_id, "destination_id": destination_id},
        )

    if not record:
        api_error(
            "INTERNAL_ERROR",
            "Upsert failed",
            {"recordset_id": recordset_id, "destination_id": destination_id},
            500,
        )

    return item_response(record[0])


@router.delete("/recordsets/{recordset_id}/destinations/{destination_id}")
# Remove a destination configuration from a recordset. If the deleted row was
# the default and others remain, promote the lowest destination_id to default
# -- a recordset with any destinations should never be left with none marked
# default. The user can re-pick the right one afterward via the edit modal.
async def delete_recordset_destination(recordset_id: int, destination_id: int, db: Database = Depends()):
    try:
        async with db.transaction() as conn:
            rows = await conn.fetch(
                """
                delete from recordset_destination
                where recordset_id = $1 and destination_id = $2
                returning recordset_id, destination_id, default_display
                """,
                recordset_id, destination_id,
            )

            if rows and rows[0]["default_display"]:
                await conn.execute(
                    """
                    update recordset_destination
                    set default_display = true
                    where recordset_id = $1
                      and destination_id = (
                          select destination_id
                          from recordset_destination
                          where recordset_id = $1
                          order by destination_id
                          limit 1
                      )
                    """,
                    recordset_id,
                )
    except Exception as e:
        db_error(
            e,
            operation="deleting recordset destination",
            context={"recordset_id": recordset_id, "destination_id": destination_id},
        )

    if not rows:
        api_error(
            "NOT_FOUND",
            "Destination configuration not found",
            {"recordset_id": recordset_id, "destination_id": destination_id},
            404,
        )

    return item_response({"deleted": True, "recordset_id": recordset_id, "destination_id": destination_id})

# -----------------------------------------RECORDSET DRAFTS-----------------------------------------------

@router.post("/recordsets/{recordset_id}/drafts")
# Create one recordset draft from any single source -- an activity timepoint, a
# previous release (clone), or empty. Auto-names when no name is given and
# enforces one open draft per recordset (the policy the cycle view assumes).
async def create_recordset_draft(
    recordset_id: int,
    payload: RecordsetDraftInsert,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if payload.activity_timepoint_id is not None and payload.cloned_from_release_id is not None:
        api_error(
            "VALIDATION_ERROR",
            "A draft has a single source: provide activity_timepoint_id OR cloned_from_release_id, not both",
            {
                "activity_timepoint_id": payload.activity_timepoint_id,
                "cloned_from_release_id": payload.cloned_from_release_id,
            },
            422,
        )

    open_draft_q = """
        select recordset_draft_id from recordset_draft
        where recordset_id = $1 and draft_status not in ('published', 'deleted')
        limit 1
        """
    latest_release_q = """
        select recordset_release_id, release_number
        from recordset_release
        where recordset_id = $1
        order by release_number desc
        limit 1
        """
    timepoint_q = "select activity_timepoint_id from activity_timepoint where activity_timepoint_id = $1"
    validate_release_q = "select 1 from recordset_release where recordset_release_id = $1 limit 1"
    insert_draft_q = """\
        insert into recordset_draft (
            recordset_id, cloned_from_release_id, draft_name, draft_notes, draft_status,
            when_created, when_updated, who_created, who_updated
        )
        values ($1, $2, $3, $4, $5, now(), now(), $6, $6)
        returning *;
    """
    # Non-DICOM files carry their file_import name; DICOM stays null (see the
    # add_dataset_module_tables DDL / file-name notes).
    populate_from_timepoint_q = """
        insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
        select $1, atf.file_id,
               case when f.is_dicom_file then null
                    else (select fi.file_name
                          from file_import fi
                          where fi.file_id = atf.file_id
                          order by fi.file_import_time desc nulls last, fi.import_event_id desc
                          limit 1)
               end
        from activity_timepoint_file atf
        join file f on f.file_id = atf.file_id
        where atf.activity_timepoint_id = $2
        """
    clone_from_release_q = """\
        insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
        select $1, rrf.file_id, rrf.file_name
        from recordset_release_file rrf
        where rrf.recordset_release_id = $2
        on conflict (recordset_draft_id, file_id, file_name) do nothing;
    """
    count_q = "select count(*)::int as file_count from recordset_draft_file where recordset_draft_id = $1"

    try:
        async with db.transaction() as conn:
            # One open draft per recordset.
            existing = await conn.fetch(open_draft_q, recordset_id)
            if existing:
                api_error(
                    "CONFLICT",
                    "Recordset already has an open draft",
                    {"recordset_id": recordset_id, "recordset_draft_id": existing[0]["recordset_draft_id"]},
                    409,
                )

            # Validate the chosen source before writing anything.
            if payload.activity_timepoint_id is not None:
                if not await conn.fetch(timepoint_q, payload.activity_timepoint_id):
                    api_error("NOT_FOUND", "Timepoint not found",
                              {"activity_timepoint_id": payload.activity_timepoint_id}, 404)
            if payload.cloned_from_release_id is not None:
                if not await conn.fetch(validate_release_q, payload.cloned_from_release_id):
                    api_error("VALIDATION_ERROR", "Invalid cloned_from_release_id",
                              {"cloned_from_release_id": payload.cloned_from_release_id}, 422)

            latest = await conn.fetch(latest_release_q, recordset_id)
            next_number = (latest[0]["release_number"] + 1) if latest else None

            draft_name = (payload.draft_name or "").strip() or (
                f"Version {next_number} Draft" if next_number else "Initial Draft"
            )

            # Provenance: an explicit release for a clone; otherwise the latest
            # release as the staleness baseline (mirrors the cycle endpoint).
            cloned_from = payload.cloned_from_release_id
            if cloned_from is None and payload.activity_timepoint_id is not None:
                cloned_from = latest[0]["recordset_release_id"] if latest else None

            record = await conn.fetch(
                insert_draft_q,
                recordset_id,
                cloned_from,
                draft_name,
                payload.draft_notes,
                payload.draft_status,
                current_user.user_id,
            )
            draft_id = record[0]["recordset_draft_id"]

            if payload.activity_timepoint_id is not None:
                await conn.execute(populate_from_timepoint_q, draft_id, payload.activity_timepoint_id)
            elif payload.cloned_from_release_id is not None:
                await conn.execute(clone_from_release_q, draft_id, payload.cloned_from_release_id)

            counted = await conn.fetch(count_q, draft_id)
    except HTTPException:
        raise
    except Exception as e:
        db_error(
            e,
            operation="creating recordset draft",
            context={"recordset_id": recordset_id},
        )

    result = dict(record[0])
    result["file_count"] = counted[0]["file_count"] if counted else 0
    return item_response(result)


@router.get("/recordsets/drafts/{draft_id}")
# Get draft detail
async def get_recordset_draft(
    draft_id: int,
    db: Database = Depends()):

    query = """\
        select
            rd.recordset_draft_id,
            rd.recordset_id,
            rd.cloned_from_release_id,
            rd.draft_name,
            rd.draft_status,
            rd.draft_notes,
            rd.when_created,
            rd.who_created,
            rd.when_updated,
            rd.who_updated
        from
            recordset_draft rd
        where
            rd.recordset_draft_id = $1;
        """
    try:
        record = await db.fetch_one(query, [draft_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset draft",
            context={"draft_id": draft_id},
        )

    if not record:
        api_error("NOT_FOUND", "Recordset draft not found", {"draft_id": draft_id}, 404)

    return item_response(record)


@router.put("/recordsets/drafts/{draft_id}")
# Update draft metadata
async def update_recordset_draft(
    draft_id: int,
    payload: RecordsetDraftUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updates = []
    values = []
    idx = 1

    if payload.recordset_id is not None:
        updates.append(f"recordset_id = ${idx}")
        values.append(payload.recordset_id)
        idx += 1

    if payload.draft_name is not None:
        updates.append(f"draft_name = ${idx}")
        values.append(payload.draft_name)
        idx += 1

    if payload.draft_notes is not None:
        updates.append(f"draft_notes = ${idx}")
        values.append(payload.draft_notes)
        idx += 1

    if payload.draft_status is not None:
        updates.append(f"draft_status = ${idx}")
        values.append(payload.draft_status)
        idx += 1

    if payload.cloned_from_release_id is not None:
        updates.append(f"cloned_from_release_id = ${idx}")
        values.append(payload.cloned_from_release_id)
        idx += 1

    if not updates:
        api_error("VALIDATION_ERROR", "No recordset draft fields were provided", {}, 422)

    updates.append("when_updated = now()")
    updates.append(f"who_updated = ${idx}")
    values.append(current_user.user_id)
    idx += 1

    draft_id_placeholder = idx

    query = f"""\
        update
            recordset_draft
            set {', '.join(updates)}
            where recordset_draft_id = ${draft_id_placeholder}
        returning *;
    """
    values.append(draft_id)

    try:
        record = await db.fetch_one(query, values)
    except Exception as e:
        db_error(e, operation="updating recordset draft", context={"draft_id": draft_id})

    if not record:
        api_error("NOT_FOUND", "Draft recordset not found", {"draft_id": draft_id}, 404)

    return item_response(record)


@router.delete("/recordsets/drafts/{draft_id}")
# Delete draft
async def delete_recordset_draft(
    draft_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    delete_query = """\
        update recordset_draft
        set
            draft_status = 'deleted',
            when_updated = now(),
            who_updated = $2
        where recordset_draft_id = $1
        returning *;
    """

    try:
        record = await db.fetch_one(delete_query, [draft_id, current_user.user_id])
    except Exception as e:
        db_error(
            e,
            operation="deleting recordset draft",
            context={"draft_id": draft_id},
        )

    if not record:
        api_error("NOT_FOUND", "Draft not found", {"draft_id": draft_id}, 404)

    return item_response(record)


@router.get("/recordsets/drafts/{draft_id}/files")
# List files in a draft. `dicom` filters to DICOM (true) or non-DICOM (false,
# treating unprocessed/null as non-DICOM); omit for all.
async def get_recordset_draft_files(
    draft_id: int,
    dicom: Optional[bool] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    if dicom is True:
        dicom_clause = "and f.is_dicom_file = true"
    elif dicom is False:
        dicom_clause = "and coalesce(f.is_dicom_file, false) = false"
    else:
        dicom_clause = ""

    list_q = f"""\
        select rf.recordset_draft_file_id, rf.file_id, rf.file_name,
               f.size, f.file_type, f.is_dicom_file
        from recordset_draft_file rf
        join file f using (file_id)
        where rf.recordset_draft_id = $1
        {dicom_clause}
        order by rf.file_name nulls first, rf.file_id
        {page_clause(page, limit)}
        """
    count_q = f"""\
        select count(*) as total
        from recordset_draft_file rf
        join file f using (file_id)
        where rf.recordset_draft_id = $1
        {dicom_clause}
        """

    try:
        records = await db.fetch(list_q, [draft_id])
        total = (await db.fetch(count_q, [draft_id]))[0]["total"]
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset draft files",
            context={"draft_id": draft_id},
        )

    return paged_response(records, total, page, limit)


@router.get("/recordsets/drafts/{draft_id}/summary")
async def get_recordset_draft_summary(
    draft_id: int,
    db: Database = Depends()):

    q_check = """
        select recordset_draft_id
        from recordset_draft
        where recordset_draft_id = $1
    """

    q_by_type = """
        select
            coalesce(f.file_type, 'unknown') as file_type,
            count(*)::int                     as file_count,
            coalesce(sum(f.size), 0)::bigint  as total_size_bytes
        from recordset_draft_file rdf
        join file f using (file_id)
        where rdf.recordset_draft_id = $1
        group by f.file_type
        order by file_count desc
    """

    q_dicom = """
        select
            count(distinct fp.patient_id)::int          as patient_count,
            count(distinct fs.study_instance_uid)::int  as study_count,
            count(distinct fse.series_instance_uid)::int as series_count
        from recordset_draft_file rdf
        join file f using (file_id)
        left join file_patient  fp  using (file_id)
        left join file_study    fs  using (file_id)
        left join file_series   fse using (file_id)
        where rdf.recordset_draft_id = $1
          and f.is_dicom_file = true
    """

    q_modality = """
        select
            coalesce(fse.modality, 'unknown')            as modality,
            count(distinct fse.series_instance_uid)::int as series_count,
            count(*)::int                                as file_count
        from recordset_draft_file rdf
        join file f using (file_id)
        join file_series fse using (file_id)
        where rdf.recordset_draft_id = $1
          and f.is_dicom_file = true
        group by fse.modality
        order by series_count desc
    """

    try:
        draft = await db.fetch_one(q_check, [draft_id])
        if not draft:
            api_error("NOT_FOUND", "Recordset draft not found", {"draft_id": draft_id}, 404)

        by_type   = await db.fetch(q_by_type,  [draft_id])
        dicom     = await db.fetch_one(q_dicom, [draft_id])
        modalities = await db.fetch(q_modality, [draft_id])
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="fetching draft summary", context={"draft_id": draft_id})

    return item_response({
        "draft_id":         draft_id,
        "total_files":      sum(r["file_count"] for r in by_type),
        "total_size_bytes": sum(r["total_size_bytes"] for r in by_type),
        "by_file_type":     [dict(r) for r in by_type],
        "dicom": {
            "patient_count":  dicom["patient_count"],
            "study_count":    dicom["study_count"],
            "series_count":   dicom["series_count"],
            "by_modality":    [dict(r) for r in modalities],
        },
    })



@router.post("/recordsets/drafts/{draft_id}/files/add")
# Add files to a draft
async def add_recordset_draft_files(
    draft_id: int,
    payload: RecordsetDraftFileAdd,
    db: Database = Depends()):

    # $3 = caller-supplied name; when null, fall back to the file's most-recent
    # file_import name for non-DICOM files (DICOM stays null). The same file_id
    # may be added more than once under different names -- the unique index is
    # on (recordset_draft_id, file_id, file_name), so only an exact repeat of a
    # (file, name) pair is skipped.
    add_query = """
            insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
            values ($1, $2, coalesce($3,
                (select case when f.is_dicom_file then null
                             else (select fi.file_name
                                   from file_import fi
                                   where fi.file_id = $2
                                   order by fi.file_import_time desc nulls last, fi.import_event_id desc
                                   limit 1)
                        end
                 from file f where f.file_id = $2)))
            on conflict (recordset_draft_id, file_id, file_name) do nothing
            returning recordset_draft_file_id, file_id, file_name;
        """

    count_query = """
            select count(*) as current_count
            from recordset_draft_file
            where recordset_draft_id = $1
        """

    if not payload.files:
        api_error(
            "VALIDATION_ERROR",
            "No files to add",
            {"files": []},
            422,
        )

    added = []
    skipped = []

    try:
        async with db.transaction() as conn:
            for item in payload.files:
                record = await conn.fetch(add_query, draft_id, item.file_id, item.file_name)
                if record:
                    added.append({
                        "recordset_draft_file_id": record[0]["recordset_draft_file_id"],
                        "file_id": record[0]["file_id"],
                        "file_name": record[0]["file_name"],
                    })
                else:
                    # Already present under this exact (file_id, file_name).
                    skipped.append({"file_id": item.file_id, "file_name": item.file_name})

            count_record = await conn.fetch(count_query, draft_id)
    except Exception as e:
        db_error(
            e,
            operation="adding files to recordset draft",
            context={"draft_id": draft_id},
        )

    return item_response(
        {
            "draft_id": draft_id,
            "added": added,
            "skipped": skipped,
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


@router.post("/recordsets/drafts/{draft_id}/files/remove")
# Remove files from a draft
async def remove_recordset_draft_files(
    draft_id: int,
    payload: RecordsetDraftFileRemove,
    db: Database = Depends()):

    # Remove by membership id, scoped to this draft -- deleting one named copy
    # must leave the draft's other copies of the same content intact.
    remove_query = """
            delete from recordset_draft_file
            where recordset_draft_id = $1 and recordset_draft_file_id = $2
            returning recordset_draft_file_id;
        """
    count_query = """
            select count(*) as current_count
            from recordset_draft_file
            where recordset_draft_id = $1
        """

    if not payload.recordset_draft_file_ids:
        api_error(
            "VALIDATION_ERROR",
            "No files to remove",
            {"recordset_draft_file_ids": []},
            422,
        )

    removed = []
    not_found = []

    try:
        async with db.transaction() as conn:
            for rdf_id in payload.recordset_draft_file_ids:
                record = await conn.fetch(remove_query, draft_id, rdf_id)
                if record:
                    removed.append(record[0]["recordset_draft_file_id"])
                elif rdf_id not in not_found:
                    not_found.append(rdf_id)

            count_record = await conn.fetch(count_query, draft_id)
    except Exception as e:
        db_error(
            e,
            operation="removing files from recordset draft",
            context={"draft_id": draft_id},
        )

    return item_response(
        {
            "draft_id": draft_id,
            "removed_recordset_draft_file_ids": removed,
            "not_found_recordset_draft_file_ids": not_found,
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


async def _resolve_recordset_wp_download_file(draft_id: int, db: Database):
    """Walk draft -> recordset -> linked WP download object -> download_file
    media -> source_url. Returns (source_url, file_name). Raises api_error with
    a specific 4xx at whichever link in the chain is missing."""
    draft = await db.fetch_one(
        "select recordset_id from recordset_draft where recordset_draft_id = $1",
        [draft_id],
    )
    if not draft:
        api_error("NOT_FOUND", "Recordset draft not found", {"draft_id": draft_id}, 404)

    link = await db.fetch_one(
        """
        select wp_object_id from wp_object_map
        where posda_object_type = 'recordset'
          and wp_object_type = 'download'
          and posda_object_id = $1
        """,
        [draft["recordset_id"]],
    )
    if not link:
        api_error(
            "NOT_LINKED",
            "This recordset is not linked to a WordPress download object.",
            {"recordset_id": draft["recordset_id"]},
            422,
        )
    download_object_id = link["wp_object_id"]

    try:
        download = await wp_get(f"{wp_url('Download')}/{download_object_id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    if download is None:
        api_error(
            "NOT_FOUND",
            "The linked WordPress download object was not found.",
            {"wp_download_object_id": download_object_id},
            404,
        )

    media_id = (download.get("download_file") or {}).get("ID")
    if not media_id:
        api_error(
            "NO_FILE",
            "The linked download object has no download_file attached.",
            {"wp_download_object_id": download_object_id},
            422,
        )

    try:
        media = await wp_get(f"{wp_url('Media')}/{media_id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    if media is None:
        api_error(
            "NOT_FOUND",
            "The download_file media object was not found.",
            {"media_id": media_id},
            404,
        )

    source_url = media.get("source_url")
    if not source_url:
        api_error(
            "NO_FILE",
            "The media object has no source_url to fetch.",
            {"media_id": media_id},
            422,
        )

    # The media's stored filename is the tail of its source_url.
    return source_url, os.path.basename(source_url)


@router.post("/recordsets/drafts/{draft_id}/files/from-wp")
# Pull the file attached to the recordset's WP download object into the draft.
async def add_recordset_draft_file_from_wp(
    draft_id: int,
    db: Database = Depends()):

    source_url, file_name = await _resolve_recordset_wp_download_file(draft_id, db)

    # Fetch the bytes to a temp file, hashing as we go -- mirrors importer's
    # /import/file so a WP-sourced file imports and processes identically.
    fp = tempfile.NamedTemporaryFile(dir=importer.TEMP_STORAGE_PATH, delete=False)
    m = hashlib.md5(usedforsecurity=False)
    size = 0
    try:
        async with wp_client() as client:
            async with client.stream("GET", source_url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    m.update(chunk)
                    fp.write(chunk)
                    size += len(chunk)
        fp.close()
    except httpx.HTTPStatusError as e:
        fp.close()
        os.unlink(fp.name)
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception:
        fp.close()
        os.unlink(fp.name)
        raise

    digest = m.hexdigest()

    try:
        pool = db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                created, file_id = await importer.create_or_get_file_id(digest, size, conn)
                if created:
                    root_id, _root, rel_path = await importer.copy_file_into_place(
                        fp.name, digest
                    )
                    await importer.create_file_location(file_id, root_id, rel_path, conn)
                    await importer.make_ready_to_process(file_id, conn)
                else:
                    os.unlink(fp.name)

                import_event_id = await importer.create_import_event(
                    conn, "recordset draft WP import", origin=source_url
                )
                await importer.create_file_import(file_id, import_event_id, file_name, conn)

                record = await conn.fetch(
                    """
                    insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
                    values ($1, $2, $3)
                    on conflict (recordset_draft_id, file_id, file_name) do nothing
                    returning recordset_draft_file_id, file_id, file_name
                    """,
                    draft_id, file_id, file_name,
                )
                count_record = await conn.fetch(
                    "select count(*) as current_count from recordset_draft_file where recordset_draft_id = $1",
                    draft_id,
                )
    except HTTPException:
        raise
    except Exception as e:
        db_error(
            e,
            operation="importing WordPress file into recordset draft",
            context={"draft_id": draft_id, "source_url": source_url},
        )

    return item_response(
        {
            "draft_id": draft_id,
            "file_id": file_id,
            "file_name": file_name,
            "created": created,
            "added": bool(record),
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


class DraftDiffResponse(BaseModel):
    draft_id: int
    compare_type: str  # "release" | "draft" | "activity"
    compare_id: int
    compare_timepoint_id: Optional[int] = None
    added_file_ids: list[int]
    removed_file_ids: list[int]
    added_count: int
    removed_count: int
    unchanged_count: int


class SeriesApplyEntry(BaseModel):
    activity_series_uid: str
    action: str  # "replace" | "add"
    target_series_uid: Optional[str] = None  # required when action == "replace"


class SeriesApplyRequest(BaseModel):
    compare_timepoint_id: int
    compare_activity_id: Optional[int] = None
    entries: list[SeriesApplyEntry] = []
    # Also pull the activity's non-DICOM files not already in the draft.
    include_non_dicom: bool = False


# Insert one activity series' files into the draft (DICOM -> null name). Shared
# by replace and add; on conflict skips an exact (file, name) repeat.
_INSERT_SERIES_FILES_Q = """
    insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
    select $1, atf.file_id,
           case when f.is_dicom_file then null
                else (select fi.file_name
                      from file_import fi
                      where fi.file_id = atf.file_id
                      order by fi.file_import_time desc nulls last, fi.import_event_id desc
                      limit 1)
           end
    from activity_timepoint_file atf
    join file f          on f.file_id = atf.file_id
    join file_series fse on fse.file_id = atf.file_id
    where atf.activity_timepoint_id = $2 and fse.series_instance_uid = $3
    on conflict (recordset_draft_id, file_id, file_name) do nothing
    returning recordset_draft_file_id
"""

_DELETE_SERIES_FILES_Q = """
    delete from recordset_draft_file
    where recordset_draft_id = $1
      and file_id in (select file_id from file_series where series_instance_uid = $2)
    returning recordset_draft_file_id
"""

_INSERT_NON_DICOM_Q = """
    insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
    select $1, atf.file_id,
           (select fi.file_name
            from file_import fi
            where fi.file_id = atf.file_id
            order by fi.file_import_time desc nulls last, fi.import_event_id desc
            limit 1)
    from activity_timepoint_file atf
    join file f on f.file_id = atf.file_id
    where atf.activity_timepoint_id = $2 and coalesce(f.is_dicom_file, false) = false
    on conflict (recordset_draft_id, file_id, file_name) do nothing
    returning recordset_draft_file_id
"""


@router.post("/recordsets/drafts/{draft_id}/series/apply")
# Apply an activity's DICOM series to the draft: per entry, replace (remove the
# target series' files, add the activity series') or add. All-or-nothing so a
# partial correction can't land. Other series in the draft are untouched.
async def apply_recordset_draft_series(
    draft_id: int,
    payload: SeriesApplyRequest,
    db: Database = Depends()):

    if not payload.entries and not payload.include_non_dicom:
        api_error("VALIDATION_ERROR", "Nothing to apply", {"entries": []}, 422)

    for entry in payload.entries:
        if entry.action not in ("replace", "add"):
            api_error(
                "VALIDATION_ERROR",
                f"Unknown action '{entry.action}'",
                {"activity_series_uid": entry.activity_series_uid},
                422,
            )
        if entry.action == "replace" and not entry.target_series_uid:
            api_error(
                "VALIDATION_ERROR",
                "target_series_uid is required to replace a series",
                {"activity_series_uid": entry.activity_series_uid},
                422,
            )

    draft = await db.fetch_one(
        "select recordset_draft_id from recordset_draft where recordset_draft_id = $1",
        [draft_id],
    )
    if not draft:
        api_error("NOT_FOUND", "Recordset draft not found", {"draft_id": draft_id}, 404)

    if payload.compare_activity_id is not None:
        tp = await db.fetch_one(
            """
            select activity_timepoint_id from activity_timepoint
            where activity_timepoint_id = $1 and activity_id = $2
            """,
            [payload.compare_timepoint_id, payload.compare_activity_id],
        )
        if tp is None:
            api_error(
                "NOT_FOUND",
                f"Timepoint {payload.compare_timepoint_id} not found for activity {payload.compare_activity_id}",
                {"compare_timepoint_id": payload.compare_timepoint_id},
                404,
            )

    series_replaced = 0
    series_added = 0
    files_removed = 0
    files_added = 0
    non_dicom_added = 0

    try:
        async with db.transaction() as conn:
            for entry in payload.entries:
                if entry.action == "replace":
                    removed = await conn.fetch(
                        _DELETE_SERIES_FILES_Q, draft_id, entry.target_series_uid
                    )
                    files_removed += len(removed)
                    series_replaced += 1
                else:
                    series_added += 1

                added = await conn.fetch(
                    _INSERT_SERIES_FILES_Q,
                    draft_id,
                    payload.compare_timepoint_id,
                    entry.activity_series_uid,
                )
                files_added += len(added)

            if payload.include_non_dicom:
                nd = await conn.fetch(
                    _INSERT_NON_DICOM_Q, draft_id, payload.compare_timepoint_id
                )
                non_dicom_added = len(nd)

            count_record = await conn.fetch(
                "select count(*) as current_count from recordset_draft_file where recordset_draft_id = $1",
                draft_id,
            )
    except HTTPException:
        raise
    except Exception as e:
        db_error(
            e,
            operation="applying series to recordset draft",
            context={"draft_id": draft_id},
        )

    return item_response({
        "draft_id": draft_id,
        "series_replaced": series_replaced,
        "series_added": series_added,
        "files_removed": files_removed,
        "files_added": files_added,
        "non_dicom_added": non_dicom_added,
        "current_count": count_record[0]["current_count"] if count_record else 0,
    })


# --- Series-level reconcile: counts + search + bulk operations ---------------
# Lists don't scale (a dataset can have thousands of series), so the UI works
# from counts (series-summary) and a filtered, paged search (series-search); the
# write ops below are all server-computed set operations by SeriesInstanceUID.

# DICOM series UIDs present in an activity timepoint / a draft.
_SOURCE_UIDS = """
    select distinct fse.series_instance_uid
    from activity_timepoint_file atf
    join file f          on f.file_id = atf.file_id and f.is_dicom_file = true
    join file_series fse on fse.file_id = atf.file_id
    where atf.activity_timepoint_id = $2
"""
_DRAFT_UIDS = """
    select distinct fse.series_instance_uid
    from recordset_draft_file rdf
    join file f          on f.file_id = rdf.file_id and f.is_dicom_file = true
    join file_series fse on fse.file_id = rdf.file_id
    where rdf.recordset_draft_id = $1
"""

# Series present in BOTH the draft and the timepoint whose file sets actually
# differ (files are content-addressed, so a differing file_id == changed content).
# Matched-but-identical series are excluded -- re-adding them would be no-op churn.
# $1 draft, $2 timepoint.
_CHANGED_SERIES_UIDS = """
    with draft_sf as (
        select fse.series_instance_uid as uid, rdf.file_id
        from recordset_draft_file rdf
        join file f          on f.file_id = rdf.file_id and f.is_dicom_file = true
        join file_series fse on fse.file_id = rdf.file_id
        where rdf.recordset_draft_id = $1
    ),
    source_sf as (
        select fse.series_instance_uid as uid, atf.file_id
        from activity_timepoint_file atf
        join file f          on f.file_id = atf.file_id and f.is_dicom_file = true
        join file_series fse on fse.file_id = atf.file_id
        where atf.activity_timepoint_id = $2
    ),
    matched as (
        select uid from draft_sf intersect select uid from source_sf
    )
    select distinct uid from (
        select uid, file_id from draft_sf  except select uid, file_id from source_sf
        union all
        select uid, file_id from source_sf except select uid, file_id from draft_sf
    ) diff
    where uid in (select uid from matched)
"""

# Insert an activity timepoint's DICOM files for the given series UIDs (DICOM ->
# null name). $1 draft, $2 timepoint, $3 uid array.
_INSERT_SOURCE_SERIES_BY_UIDS = """
    insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
    select $1, atf.file_id,
           case when f.is_dicom_file then null
                else (select fi.file_name from file_import fi
                      where fi.file_id = atf.file_id
                      order by fi.file_import_time desc nulls last, fi.import_event_id desc
                      limit 1)
           end
    from activity_timepoint_file atf
    join file f          on f.file_id = atf.file_id
    join file_series fse on fse.file_id = atf.file_id
    where atf.activity_timepoint_id = $2 and fse.series_instance_uid = any($3::text[])
    on conflict (recordset_draft_id, file_id, file_name) do nothing
    returning recordset_draft_file_id
"""

# Delete a draft's files for the given series UIDs. $1 draft, $2 uid array.
_DELETE_DRAFT_SERIES_BY_UIDS = """
    delete from recordset_draft_file rdf
    using file_series fse
    where rdf.recordset_draft_id = $1
      and fse.file_id = rdf.file_id
      and fse.series_instance_uid = any($2::text[])
    returning rdf.recordset_draft_file_id
"""


async def _require_timepoint(db, timepoint_id: int, activity_id: Optional[int]):
    if activity_id is None:
        tp = await db.fetch_one(
            "select activity_timepoint_id from activity_timepoint where activity_timepoint_id = $1",
            [timepoint_id],
        )
    else:
        tp = await db.fetch_one(
            "select activity_timepoint_id from activity_timepoint where activity_timepoint_id = $1 and activity_id = $2",
            [timepoint_id, activity_id],
        )
    if tp is None:
        api_error("NOT_FOUND", f"Timepoint {timepoint_id} not found", {"compare_timepoint_id": timepoint_id}, 404)


async def _require_draft(db, draft_id: int):
    draft = await db.fetch_one(
        "select recordset_draft_id from recordset_draft where recordset_draft_id = $1",
        [draft_id],
    )
    if not draft:
        api_error("NOT_FOUND", "Recordset draft not found", {"draft_id": draft_id}, 404)


@router.get("/recordsets/drafts/{draft_id}/series-summary")
async def get_recordset_draft_series_summary(
    draft_id: int,
    compare_timepoint_id: int,
    compare_activity_id: Optional[int] = None,
    db: Database = Depends()):
    """Counts for a source-vs-draft series reconcile -- no lists, so it scales.
    Drives the Merge / Replace-all previews."""
    await _require_draft(db, draft_id)
    await _require_timepoint(db, compare_timepoint_id, compare_activity_id)

    q = f"""
        with s as ({_SOURCE_UIDS}), d as ({_DRAFT_UIDS})
        select
            (select count(*) from s) as source_series_count,
            (select count(*) from d) as draft_series_count,
            (select count(*) from (select * from s intersect select * from d) x) as matching_series_count,
            (select count(*) from (select * from s except    select * from d) x) as new_series_count,
            (select count(*) from (select * from d except    select * from s) x) as draft_only_series_count,
            (select count(*) from activity_timepoint_file atf
               join file f on f.file_id = atf.file_id and f.is_dicom_file = true
               where atf.activity_timepoint_id = $2) as source_dicom_file_count,
            (select count(*) from recordset_draft_file rdf
               join file f on f.file_id = rdf.file_id and f.is_dicom_file = true
               where rdf.recordset_draft_id = $1) as draft_dicom_file_count,
            (select count(*) from activity_timepoint_file atf
               join file f on f.file_id = atf.file_id
               where atf.activity_timepoint_id = $2 and coalesce(f.is_dicom_file, false) = false)
               as source_non_dicom_file_count,
            (select count(*) from recordset_draft_file rdf
               join file f on f.file_id = rdf.file_id
               where rdf.recordset_draft_id = $1 and coalesce(f.is_dicom_file, false) = false)
               as draft_non_dicom_file_count,
            (select count(*) from (
                select atf.file_id from activity_timepoint_file atf
                join file f on f.file_id = atf.file_id
                where atf.activity_timepoint_id = $2 and coalesce(f.is_dicom_file, false) = false
                except
                select rdf.file_id from recordset_draft_file rdf where rdf.recordset_draft_id = $1
            ) x) as non_dicom_to_add
    """
    try:
        row = await db.fetch_one(q, [draft_id, compare_timepoint_id])
        changed = await db.fetch(_CHANGED_SERIES_UIDS, [draft_id, compare_timepoint_id])
    except Exception as e:
        db_error(e, operation="summarizing draft series", context={"draft_id": draft_id})

    changed_count = len(changed)
    return item_response({
        "draft_id": draft_id,
        **dict(row),
        # Of the matching series, only these have differing files (worth updating).
        "changed_series_count": changed_count,
        "unchanged_series_count": row["matching_series_count"] - changed_count,
    })


@router.get("/recordsets/drafts/{draft_id}/series-search")
async def search_recordset_draft_series(
    draft_id: int,
    scope: str = Query(..., pattern="^(source|draft)$"),
    granularity: str = Query("series", pattern="^(series|files)$"),
    compare_timepoint_id: Optional[int] = None,
    compare_activity_id: Optional[int] = None,
    patient_id: Optional[str] = None,
    study_instance_uid: Optional[str] = None,
    series_instance_uid: Optional[str] = None,
    sop_instance_uid: Optional[str] = None,
    file_id: Optional[int] = None,
    page: Optional[int] = Query(default=1),
    limit: Optional[int] = Query(default=50),
    db: Database = Depends()):
    """Find the DICOM series (or, with granularity=files, individual draft files)
    whose files match any combination of identifiers -- patient / study / series /
    SOP instance UID (ILIKE partials) or an exact Posda file_id. `granularity=files`
    lists each instance (for per-file removal via the series drill-in) and matches
    series_instance_uid exactly; it is draft-only. At least one identifier required."""
    await _require_draft(db, draft_id)
    if scope == "source":
        if compare_timepoint_id is None:
            api_error("VALIDATION_ERROR", "compare_timepoint_id is required for scope=source", {}, 422)
        await _require_timepoint(db, compare_timepoint_id, compare_activity_id)
    if granularity == "files" and scope != "draft":
        api_error("VALIDATION_ERROR", "granularity=files is only valid for scope=draft", {}, 422)

    if not any([patient_id, study_instance_uid, series_instance_uid, sop_instance_uid, file_id]):
        api_error("VALIDATION_ERROR", "Provide at least one search identifier", {}, 422)

    # Inline the validated ints; bind the raw filter values ($1-$5) and wrap for
    # ILIKE in SQL, so every query references the same dense parameter set.
    draft = int(draft_id)
    if scope == "source":
        src_from = "activity_timepoint_file sf"
        scope_where = f"sf.activity_timepoint_id = {int(compare_timepoint_id)}"
    else:
        src_from = "recordset_draft_file sf"
        scope_where = f"sf.recordset_draft_id = {draft}"

    # Files granularity drills into one exact series; series granularity is a
    # forgiving partial match.
    series_match = (
        "fse.series_instance_uid = $3" if granularity == "files"
        else "fse.series_instance_uid ilike '%'||$3||'%'"
    )
    filt = f"""
        and ($1::text is null or fp.patient_id ilike '%'||$1||'%')
        and ($2::text is null or fs.study_instance_uid ilike '%'||$2||'%')
        and ($3::text is null or {series_match})
        and ($4::text is null or fsc.sop_instance_uid ilike '%'||$4||'%')
        and ($5::int  is null or sf.file_id = $5)
    """
    args = [patient_id, study_instance_uid, series_instance_uid, sop_instance_uid, file_id]

    if granularity == "files":
        # Draft-only: one row per membership, so removal can target the instance.
        common_from = f"""
            from recordset_draft_file sf
            join file f            on f.file_id = sf.file_id and f.is_dicom_file = true
            join file_series fse   on fse.file_id = sf.file_id
            left join file_patient fp  on fp.file_id = sf.file_id
            left join file_study   fs  on fs.file_id = sf.file_id
            left join file_sop_common fsc on fsc.file_id = sf.file_id
            where sf.recordset_draft_id = {draft} {filt}
        """
        list_q = f"""
            select sf.recordset_draft_file_id, sf.file_id,
                   fsc.sop_instance_uid, fse.series_instance_uid,
                   fse.modality, fse.series_number, fse.series_description, fp.patient_id
            {common_from}
            order by fse.series_instance_uid, fsc.sop_instance_uid nulls last, sf.file_id
            {page_clause(page, limit)}
        """
        count_q = f"select count(*) as total {common_from}"
    else:
        # A file (in scope) matching all provided identifiers pins its series.
        matching = f"""
            select distinct fse.series_instance_uid
            from {src_from}
            join file f            on f.file_id = sf.file_id and f.is_dicom_file = true
            join file_series fse   on fse.file_id = sf.file_id
            left join file_patient fp  on fp.file_id = sf.file_id
            left join file_study   fs  on fs.file_id = sf.file_id
            left join file_sop_common fsc on fsc.file_id = sf.file_id
            where {scope_where} {filt}
        """
        list_q = f"""
            with matching as ({matching})
            select fse.series_instance_uid,
                   max(fse.modality) as modality, max(fse.series_number) as series_number,
                   max(fse.series_description) as series_description,
                   max(fp.patient_id) as patient_id, max(fs.study_instance_uid) as study_instance_uid,
                   count(distinct sf.file_id) as file_count
            from {src_from}
            join file f          on f.file_id = sf.file_id and f.is_dicom_file = true
            join file_series fse on fse.file_id = sf.file_id
            left join file_patient fp on fp.file_id = sf.file_id
            left join file_study   fs on fs.file_id = sf.file_id
            where {scope_where}
              and fse.series_instance_uid in (select series_instance_uid from matching)
            group by fse.series_instance_uid
            order by max(fp.patient_id) nulls last, max(fse.series_number) nulls last, fse.series_instance_uid
            {page_clause(page, limit)}
        """
        count_q = f"select count(*) as total from ({matching}) m"

    try:
        rows = await db.fetch(list_q, args)
        total = (await db.fetch(count_q, args))[0]["total"]
    except Exception as e:
        db_error(e, operation="searching draft series", context={"draft_id": draft_id})

    return paged_response(rows, total, page, limit)


class SeriesMergeRequest(BaseModel):
    compare_timepoint_id: int
    compare_activity_id: Optional[int] = None
    add_new: bool = True
    update_matching: bool = True
    include_non_dicom: bool = False


@router.post("/recordsets/drafts/{draft_id}/series/merge")
# Merge an activity into the draft: optionally add series not yet in the draft
# and/or replace the files of series already in it (matched by UID). One
# transaction; series only in the draft are left alone.
async def merge_recordset_draft_series(
    draft_id: int,
    payload: SeriesMergeRequest,
    db: Database = Depends()):

    if not payload.add_new and not payload.update_matching and not payload.include_non_dicom:
        api_error("VALIDATION_ERROR", "Nothing selected to merge", {}, 422)

    await _require_draft(db, draft_id)
    await _require_timepoint(db, payload.compare_timepoint_id, payload.compare_activity_id)

    tp = payload.compare_timepoint_id
    series_updated = series_added = files_removed = files_added = non_dicom_added = 0

    try:
        async with db.transaction() as conn:
            # Capture the changed/new UID sets before any delete changes
            # membership. "Update matching" only touches series whose files
            # actually differ -- identical series are skipped, not re-added.
            changed = [r["uid"] for r in await conn.fetch(
                _CHANGED_SERIES_UIDS, draft_id, tp)]
            new = [r["series_instance_uid"] for r in await conn.fetch(
                f"{_SOURCE_UIDS} except {_DRAFT_UIDS}", draft_id, tp)]

            if payload.update_matching and changed:
                removed = await conn.fetch(_DELETE_DRAFT_SERIES_BY_UIDS, draft_id, changed)
                files_removed += len(removed)
                added = await conn.fetch(_INSERT_SOURCE_SERIES_BY_UIDS, draft_id, tp, changed)
                files_added += len(added)
                series_updated = len(changed)

            if payload.add_new and new:
                added = await conn.fetch(_INSERT_SOURCE_SERIES_BY_UIDS, draft_id, tp, new)
                files_added += len(added)
                series_added = len(new)

            if payload.include_non_dicom:
                nd = await conn.fetch(_INSERT_NON_DICOM_Q, draft_id, tp)
                non_dicom_added = len(nd)

            current = (await conn.fetch(
                "select count(*) as c from recordset_draft_file where recordset_draft_id = $1", draft_id))[0]["c"]
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="merging series into recordset draft", context={"draft_id": draft_id})

    return item_response({
        "draft_id": draft_id,
        "series_updated": series_updated,
        "series_added": series_added,
        "files_removed": files_removed,
        "files_added": files_added,
        "non_dicom_added": non_dicom_added,
        "current_count": current,
    })


class SeriesReplaceAllRequest(BaseModel):
    compare_timepoint_id: int
    compare_activity_id: Optional[int] = None


@router.post("/recordsets/drafts/{draft_id}/content/replace-all")
# Destructive: replace the entire draft's contents with an activity timepoint's.
async def replace_all_recordset_draft(
    draft_id: int,
    payload: SeriesReplaceAllRequest,
    db: Database = Depends()):

    await _require_draft(db, draft_id)
    await _require_timepoint(db, payload.compare_timepoint_id, payload.compare_activity_id)

    try:
        async with db.transaction() as conn:
            removed = await conn.fetch(
                "delete from recordset_draft_file where recordset_draft_id = $1 returning recordset_draft_file_id",
                draft_id,
            )
            added = await conn.fetch(
                """
                insert into recordset_draft_file (recordset_draft_id, file_id, file_name)
                select $1, atf.file_id,
                       case when f.is_dicom_file then null
                            else (select fi.file_name from file_import fi
                                  where fi.file_id = atf.file_id
                                  order by fi.file_import_time desc nulls last, fi.import_event_id desc
                                  limit 1)
                       end
                from activity_timepoint_file atf
                join file f on f.file_id = atf.file_id
                where atf.activity_timepoint_id = $2
                on conflict (recordset_draft_id, file_id, file_name) do nothing
                returning recordset_draft_file_id
                """,
                draft_id, payload.compare_timepoint_id,
            )
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="replacing recordset draft contents", context={"draft_id": draft_id})

    return item_response({
        "draft_id": draft_id,
        "files_removed": len(removed),
        "files_added": len(added),
        "current_count": len(added),
    })


class SeriesRemoveRequest(BaseModel):
    series_uids: list[str]


@router.post("/recordsets/drafts/{draft_id}/series/remove")
# Remove entire DICOM series (by UID) from the draft -- source-independent.
async def remove_recordset_draft_series(
    draft_id: int,
    payload: SeriesRemoveRequest,
    db: Database = Depends()):

    if not payload.series_uids:
        api_error("VALIDATION_ERROR", "No series to remove", {"series_uids": []}, 422)

    await _require_draft(db, draft_id)

    try:
        async with db.transaction() as conn:
            removed = await conn.fetch(_DELETE_DRAFT_SERIES_BY_UIDS, draft_id, payload.series_uids)
            current = (await conn.fetch(
                "select count(*) as c from recordset_draft_file where recordset_draft_id = $1", draft_id))[0]["c"]
    except Exception as e:
        db_error(e, operation="removing series from recordset draft", context={"draft_id": draft_id})

    return item_response({
        "draft_id": draft_id,
        "series_removed": len(payload.series_uids),
        "files_removed": len(removed),
        "current_count": current,
    })


@router.get("/recordsets/drafts/{draft_id}/diff")
async def get_recordset_draft_diff(
    draft_id: int,
    compare_release_id: Optional[int] = None,
    compare_draft_id: Optional[int] = None,
    compare_activity_id: Optional[int] = None,
    compare_timepoint_id: Optional[int] = None,
    db: Database = Depends(),
    user: User = logged_in_user,
) -> DraftDiffResponse:
    """
    Compare a draft against a release, another draft, or an activity timepoint.

    - compare_release_id: compare against a specific release
    - compare_draft_id: compare against another draft
    - compare_activity_id: compare against an activity (uses latest timepoint if compare_timepoint_id omitted)
    - compare_timepoint_id: compare against a specific timepoint (activity_id looked up automatically if compare_activity_id omitted)

    If none are provided, defaults to the latest release for the same recordset.
    """
    draft = await db.fetch_one(
        """
        select recordset_draft_id, recordset_id
        from recordset_draft
        where recordset_draft_id = $1
        """,
        [draft_id],
    )
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    using_activity = compare_activity_id is not None or compare_timepoint_id is not None
    provided = sum([
        compare_release_id is not None,
        compare_draft_id is not None,
        using_activity,
    ])
    if provided > 1:
        raise HTTPException(
            status_code=422,
            detail="Only one of compare_release_id, compare_draft_id, or compare_activity_id/compare_timepoint_id may be provided",
        )

    added_file_ids: list[int] = []
    removed_file_ids: list[int] = []
    compare_type: str
    compare_id: int
    resolved_timepoint_id: Optional[int] = None

    if using_activity:
        compare_type = "activity"

        if compare_activity_id is not None and compare_timepoint_id is not None:
            # Both provided — validate the timepoint belongs to the activity
            tp = await db.fetch_one(
                """
                select activity_timepoint_id
                from activity_timepoint
                where activity_timepoint_id = $1 and activity_id = $2
                """,
                [compare_timepoint_id, compare_activity_id],
            )
            if tp is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Timepoint {compare_timepoint_id} not found for activity {compare_activity_id}",
                )
            resolved_timepoint_id = compare_timepoint_id
            compare_id = compare_activity_id

        elif compare_activity_id is not None:
            # Activity only — use latest timepoint
            latest_tp = await db.fetch_one(
                """
                select activity_timepoint_id
                from activity_timepoint
                where activity_id = $1
                order by when_created desc
                limit 1
                """,
                [compare_activity_id],
            )
            if latest_tp is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No timepoints found for activity {compare_activity_id}",
                )
            resolved_timepoint_id = latest_tp["activity_timepoint_id"]
            compare_id = compare_activity_id

        else:
            # Timepoint only — look up the activity
            tp = await db.fetch_one(
                """
                select activity_timepoint_id, activity_id
                from activity_timepoint
                where activity_timepoint_id = $1
                """,
                [compare_timepoint_id],
            )
            if tp is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Timepoint {compare_timepoint_id} not found",
                )
            resolved_timepoint_id = compare_timepoint_id
            compare_id = tp["activity_id"]

        added = await db.fetch(
            """
            select file_id from recordset_draft_file where recordset_draft_id = $1
            except
            select file_id from activity_timepoint_file where activity_timepoint_id = $2
            """,
            [draft_id, resolved_timepoint_id],
        )
        removed = await db.fetch(
            """
            select file_id from activity_timepoint_file where activity_timepoint_id = $1
            except
            select file_id from recordset_draft_file where recordset_draft_id = $2
            """,
            [resolved_timepoint_id, draft_id],
        )

    elif compare_draft_id is not None:
        compare_type = "draft"
        compare_id = compare_draft_id

        other = await db.fetch_one(
            "select recordset_draft_id from recordset_draft where recordset_draft_id = $1",
            [compare_draft_id],
        )
        if other is None:
            raise HTTPException(status_code=404, detail=f"Draft {compare_draft_id} not found")

        added = await db.fetch(
            """
            select file_id from recordset_draft_file where recordset_draft_id = $1
            except
            select file_id from recordset_draft_file where recordset_draft_id = $2
            """,
            [draft_id, compare_draft_id],
        )
        removed = await db.fetch(
            """
            select file_id from recordset_draft_file where recordset_draft_id = $1
            except
            select file_id from recordset_draft_file where recordset_draft_id = $2
            """,
            [compare_draft_id, draft_id],
        )

    else:
        compare_type = "release"

        if compare_release_id is None:
            latest_release = await db.fetch_one(
                """
                select recordset_release_id
                from recordset_release
                where recordset_id = $1
                order by release_number desc
                limit 1
                """,
                [draft["recordset_id"]],
            )
            if latest_release is None:
                # No prior release — everything in the draft is new
                all_files = await db.fetch(
                    "select file_id from recordset_draft_file where recordset_draft_id = $1",
                    [draft_id],
                )
                added_file_ids = [r["file_id"] for r in all_files]
                return DraftDiffResponse(
                    draft_id=draft_id,
                    compare_type="release",
                    compare_id=0,
                    added_file_ids=added_file_ids,
                    removed_file_ids=[],
                    added_count=len(added_file_ids),
                    removed_count=0,
                    unchanged_count=0,
                )
            compare_release_id = latest_release["recordset_release_id"]

        release = await db.fetch_one(
            "select recordset_release_id from recordset_release where recordset_release_id = $1",
            [compare_release_id],
        )
        if release is None:
            raise HTTPException(status_code=404, detail=f"Release {compare_release_id} not found")

        compare_id = compare_release_id

        added = await db.fetch(
            """
            select file_id from recordset_draft_file where recordset_draft_id = $1
            except
            select file_id from recordset_release_file where recordset_release_id = $2
            """,
            [draft_id, compare_release_id],
        )
        removed = await db.fetch(
            """
            select file_id from recordset_release_file where recordset_release_id = $1
            except
            select file_id from recordset_draft_file where recordset_draft_id = $2
            """,
            [compare_release_id, draft_id],
        )

    added_file_ids = [r["file_id"] for r in added]
    removed_file_ids = [r["file_id"] for r in removed]

    # unchanged_count_row = await db.fetch_one(
    #     """
    #     select count(*)::int as unchanged_count
    #     from recordset_draft_file
    #     where recordset_draft_id = $1
    #       and file_id = any($2::int[])
    #     """,
    #     [draft_id, [r["file_id"] for r in (await db.fetch(
    #         "select file_id from recordset_draft_file where recordset_draft_id = $1",
    #         [draft_id],
    #     ))]],
    # )

    total_draft = await db.fetch_one(
        "select count(*)::int as n from recordset_draft_file where recordset_draft_id = $1",
        [draft_id],
    )
    unchanged_count = (total_draft["n"] if total_draft else 0) - len(added_file_ids)

    return DraftDiffResponse(
        draft_id=draft_id,
        compare_type=compare_type,
        compare_id=compare_id,
        compare_timepoint_id=resolved_timepoint_id,
        added_file_ids=added_file_ids,
        removed_file_ids=removed_file_ids,
        added_count=len(added_file_ids),
        removed_count=len(removed_file_ids),
        unchanged_count=max(unchanged_count, 0),
    )


# TODO: This needs more thought.
# What validations do we want to perform before allowing a draft to be published?
# Do we want to block publish if there are warnings (e.g. files that are in the draft but not in the base release)?
# Do we want to allow users to override warnings and publish anyway?

# @router.post("/recordsets/drafts/{draft_id}/validate")
# # Validate draft before publish
# #   1.  Files exist in this draft
# async def validate_draft(draft_id: int, db: Database = Depends()):
#     query = """
#         select 1
#         from recordset_draft_file
#         where recordset_draft_id = $1
#         limit 1;
#     """

#     try:
#         row = await db.fetchrow(query, [draft_id])
#     except Exception as e:
#         db_error(
#             e,
#             operation="validating draft",
#             context={"draft_id": draft_id},
#         )
#         raise

#     if not row:
#         return {
#             "data": {
#                 "recordset_draft_id": draft_id,
#                 "valid": False,
#                 "errors": ["Draft has no files"],
#             }
#         }

#     return {
#         "data": {
#             "recordset_draft_id": draft_id,
#             "valid": True,
#             "errors": [],
#         }
#     }


@router.post("/recordsets/drafts/{draft_id}/publish")
# Publish a draft to an immutable recordset release
async def create_recordset_release(
    draft_id: int,
    payload: RecordsetReleaseInsert,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    q_get_recordset = """
        select recordset_id, draft_status
        from recordset_draft
        where recordset_draft_id = $1;
    """

    q_insert_release = """
        insert into recordset_release (
            recordset_id,
            release_number,
            release_date,
            release_notes,
            release_doi,
            when_created,
            who_created,
            when_updated,
            who_updated
        )
        values (
            $1,
            coalesce($2::int, (
                select coalesce(max(release_number), 0) + 1
                from recordset_release where recordset_id = $1
            )),
            coalesce($3::timestamptz, now()),
            $4, $5, now(), $6, now(), $6
        )
        returning recordset_release_id;
    """

    q_copy_files = """
        insert into recordset_release_file (recordset_release_id, file_id, file_name)
        select $1, file_id, file_name
        from recordset_draft_file
        where recordset_draft_id = $2;
    """

    q_mark_draft_published = """
        update recordset_draft
        set
            draft_status = 'published',
            when_updated = now(),
            who_updated = $2
        where recordset_draft_id = $1;
    """

    try:
        async with db.transaction() as conn:
            # 1. Get recordset_id from draft
            draft_rows = await conn.fetch(q_get_recordset, draft_id)
            if not draft_rows:
                raise HTTPException(status_code=404, detail="Draft not found")
            draft_row = draft_rows[0]

            recordset_id = draft_row["recordset_id"]

            # Publishing consumes the draft. Without this, a second call would
            # cut another release from an already-published draft -- reachable
            # by a double submit or a second caller (the Bundle stage).
            if draft_row["draft_status"] in ("published", "deleted"):
                api_error(
                    "VALIDATION_ERROR",
                    f"Draft is already {draft_row['draft_status']} and cannot be published",
                    {"draft_id": draft_id, "draft_status": draft_row["draft_status"]},
                    422,
                )

            # 2. Create release
            release_rows = await conn.fetch(
                q_insert_release,
                recordset_id,
                payload.release_number,
                payload.release_date,
                payload.release_notes,
                payload.release_doi,
                current_user.user_id,
            )

            if not release_rows:
                raise HTTPException(status_code=500, detail="Failed to create release")
            release_row = release_rows[0]

            release_id = release_row["recordset_release_id"]

            # 3. Copy files from draft → release
            await conn.execute(q_copy_files, release_id, draft_id)

            # 4. Mark draft as published
            await conn.execute(q_mark_draft_published, draft_id, current_user.user_id)

    except HTTPException:
        # Let the 404 / 422 above through; without this they are swallowed by
        # the generic handler below and re-raised as a 500.
        raise
    except Exception as e:
        db_error(
            e,
            operation="publishing recordset draft",
            context={"draft_id": draft_id},
        )
        raise

    return item_response(
        {
            "recordset_release_id": release_id,
            "recordset_id": recordset_id,
        }
    )


# -----------------------------------------RECORDSET RELEASES-----------------------------------------------

@router.get("/recordsets/releases/{release_id}")
#Get release details
async def get_recordset_release(release_id: int, db: Database = Depends()):
    query = """
        select
            r.recordset_release_id,
            r.recordset_id,
            r.release_number,
            r.release_date,
            r.release_notes,
            r.release_doi,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated,
            count(rrf.file_id)::int as file_count
        from recordset_release r
        left join recordset_release_file rrf using (recordset_release_id)
        where r.recordset_release_id = $1
        group by
            r.recordset_release_id,
            r.recordset_id,
            r.release_number,
            r.release_date,
            r.release_notes,
            r.release_doi,
            r.when_created,
            r.who_created,
            r.when_updated,
            r.who_updated;
    """

    try:
        record = await db.fetch(query, [release_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset release",
            context={"release_id": release_id},
        )

    if not record:
        api_error("NOT_FOUND", "Recordset release not found", {"release_id": release_id}, 404)

    return item_response(record[0])


@router.get("/recordsets/releases/{release_id}/files")
# List files in a release
async def get_recordset_release_files(
    release_id: int,
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    list_q = f"""\
        select rf.recordset_release_file_id, rf.file_id, rf.file_name
        from recordset_release_file rf
        where rf.recordset_release_id = $1
        order by rf.file_name nulls first, rf.file_id
        {page_clause(page, limit)}
        """
    count_q = "select count(*) as total from recordset_release_file where recordset_release_id = $1"

    try:
        records = await db.fetch(list_q, [release_id])
        total = (await db.fetch(count_q, [release_id]))[0]["total"]
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset release files",
            context={"release_id": release_id},
        )

    return paged_response(records, total, page, limit)


@router.get("/recordsets/releases/{release_id}/summary")
async def get_recordset_release_summary(release_id: int, db: Database = Depends()):
    q_check = """
        select recordset_release_id
        from recordset_release
        where recordset_release_id = $1
    """

    q_by_type = """
        select
            coalesce(f.file_type, 'unknown') as file_type,
            count(*)::int                     as file_count,
            coalesce(sum(f.size), 0)::bigint  as total_size_bytes
        from recordset_release_file rrf
        join file f using (file_id)
        where rrf.recordset_release_id = $1
        group by f.file_type
        order by file_count desc
    """

    q_dicom = """
        select
            count(distinct fp.patient_id)::int           as patient_count,
            count(distinct fs.study_instance_uid)::int   as study_count,
            count(distinct fse.series_instance_uid)::int as series_count
        from recordset_release_file rrf
        join file f using (file_id)
        left join file_patient  fp  using (file_id)
        left join file_study    fs  using (file_id)
        left join file_series   fse using (file_id)
        where rrf.recordset_release_id = $1
          and f.is_dicom_file = true
    """

    q_modality = """
        select
            coalesce(fse.modality, 'unknown')            as modality,
            count(distinct fse.series_instance_uid)::int as series_count,
            count(*)::int                                as file_count
        from recordset_release_file rrf
        join file f using (file_id)
        join file_series fse using (file_id)
        where rrf.recordset_release_id = $1
          and f.is_dicom_file = true
        group by fse.modality
        order by series_count desc
    """

    try:
        release = await db.fetch_one(q_check, [release_id])
        if not release:
            api_error("NOT_FOUND", "Recordset release not found", {"release_id": release_id}, 404)

        by_type    = await db.fetch(q_by_type,   [release_id])
        dicom      = await db.fetch_one(q_dicom,  [release_id])
        modalities = await db.fetch(q_modality,   [release_id])
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="fetching release summary", context={"release_id": release_id})

    return item_response({
        "release_id":       release_id,
        "total_files":      sum(r["file_count"] for r in by_type),
        "total_size_bytes": sum(r["total_size_bytes"] for r in by_type),
        "by_file_type":     [dict(r) for r in by_type],
        "dicom": {
            "patient_count": dicom["patient_count"],
            "study_count":   dicom["study_count"],
            "series_count":  dicom["series_count"],
            "by_modality":   [dict(r) for r in modalities],
        },
    })


#/papi/v1/distribution/recordsets/releases/{release_id}/diff/{other_release_id}
@router.get("/recordsets/releases/{release_id}/diff/{other_release_id}")
# Compare two immutable releases
async def get_release_diff(release_id: int, other_release_id: int, db: Database = Depends()):
    q_rel1_files = """
        select rf.file_id
        from recordset_release_file rf
        where rf.recordset_release_id = $1;
    """

    q_rel2_files = """
        select rf.file_id
        from recordset_release_file rf
        where rf.recordset_release_id = $1;
    """

    rel1_rows = await db.fetch(q_rel1_files, [release_id])
    rel2_rows = await db.fetch(q_rel2_files, [other_release_id])

    if not rel1_rows or not rel2_rows:
        raise HTTPException(status_code=404, detail="Base release not found")

    # Convert to sets
    rel1_file_ids = {r["file_id"] for r in rel1_rows}
    rel2_file_ids = {r["file_id"] for r in rel2_rows}

    # Diff
    added_file_ids = list(rel1_file_ids - rel2_file_ids)
    removed_file_ids = list(rel2_file_ids - rel1_file_ids)
    unchanged_count = len(rel1_file_ids & rel2_file_ids)

    records = {
        "left_release_id": release_id,
        "right_release_id": other_release_id,
        "added_file_ids": added_file_ids,
        "removed_file_ids": removed_file_ids,
        "summary": {
            "added_count": len(added_file_ids),
            "removed_count": len(removed_file_ids),
            "unchanged_count": unchanged_count,
        },
    }

    return {"data": records}


# ----------------------------------------Dataset release transfers-----------------------------------------------

@router.get("/transfers/{transfer_id}")
# Get details for a dataset release transfer
async def get_dataset_release_transfer_by_id(transfer_id: int,  db: Database = Depends()):
    query = """\
        select
            dataset_release_transfer_id,
            dataset_release_id,
            destination_id,
            transfer_name,
            transfer_mode_id,
            tm.transfer_mode_name,
            drt.destination_id,
            td.destination_name,
            td.destination_abbr,
            transfer_status,
            transfer_notes,
            when_created,
            when_updated
            from
                dataset_release_transfer drt
                join transfer_mode tm using (transfer_mode_id)
                left join transfer_destination td using (destination_id)
            where
                drt.dataset_release_transfer_id = $1;
        """
    try:
        record = await db.fetch_one(query, [transfer_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching dataset release transfer",
            context={"transfer_id": transfer_id},
        )
        api_error("DB_ERROR", "Failed to fetch transfer", {}, 500)

    if not record:
        api_error("NOT_FOUND", "Dataset release transfer not found", {"transfer_id": transfer_id}, 404)

    return item_response(record)

@router.put("/transfers/{transfer_id}")
# Update details for a dataset release transfer
async def update_dataset_release_transfer(
    transfer_id: int, payload: DatasetReleaseTransferUpdate, current_user: User = logged_in_user, db: Database = Depends()):

    # Queueing is the one-way door: it fires notify_transfer_queued() and starts
    # real uploads, with no route back through transfer_status. Refuse it while
    # the parent release is still a draft (TECH_DEBT #5) -- the contents are not
    # settled yet, and the upload cannot be recalled once it begins.
    if payload.transfer_status == "queued":
        parent = await db.fetch_one(
            """select dr.release_status
               from dataset_release_transfer drt
               join dataset_release dr using (dataset_release_id)
               where drt.dataset_release_transfer_id = $1""",
            [transfer_id],
        )
        if not parent:
            api_error(
                "NOT_FOUND",
                "Dataset release transfer not found",
                {"transfer_id": transfer_id},
                404,
            )
        if parent["release_status"] == "draft":
            api_error(
                "VALIDATION_ERROR",
                "Cannot queue a transfer for a draft release -- finalize it first",
                {"transfer_id": transfer_id, "release_status": "draft"},
                422,
            )

        # IDC reads a submission from its manifests, so queueing without them
        # ships a package it cannot interpret -- and the upload cannot be
        # recalled. This also enforces the WordPress ordering transitively: the
        # clinical manifest cannot be generated until the WordPress transfer has
        # refreshed Collection Manager (see _wp_precedence_block), so an IDC
        # transfer carrying clinical files cannot be queued before that happens.
        manifests = await _idc_manifest_state(transfer_id, db)
        if manifests and manifests["missing_manifests"]:
            api_error(
                "MANIFESTS_REQUIRED",
                "Generate this transfer's manifests before queueing it: "
                + ", ".join(manifests["missing_manifests"]),
                {"transfer_id": transfer_id, **manifests},
                422,
            )

        # base_gcs_url is filled automatically when the dataset manifest is
        # generated, but it stays editable so a package can be relocated -- and
        # an edit can blank it. Every file path the daemon uploads is relative
        # to it, so without it there is nowhere to write.
        if manifests:
            idc = await db.fetch_one(
                "select base_gcs_url from transfer_idc where dataset_release_transfer_id = $1",
                [transfer_id],
            )
            if not idc or not idc["base_gcs_url"]:
                api_error(
                    "BASE_URL_REQUIRED",
                    "This transfer has no destination bucket path -- set it before queueing",
                    {"transfer_id": transfer_id},
                    422,
                )

    updates = []
    values = []
    idx = 1

    if payload.transfer_name is not None:
        updates.append(f"transfer_name = ${idx}")
        values.append(payload.transfer_name)
        idx += 1

    if payload.transfer_mode_id is not None:
        updates.append(f"transfer_mode_id = ${idx}")
        values.append(payload.transfer_mode_id)
        idx += 1

    if payload.transfer_status is not None:
        updates.append(f"transfer_status = ${idx}")
        values.append(payload.transfer_status)
        idx += 1

    if payload.transfer_notes is not None:
        updates.append(f"transfer_notes = ${idx}")
        values.append(payload.transfer_notes)
        idx += 1

    if not updates:
        api_error("VALIDATION_ERROR", "No dataset release transfer fields were provided", {}, 422)

    updates.append("when_updated = now()")
    updates.append(f"who_updated = ${idx}")
    values.append(current_user.user_id)
    idx += 1

    transfer_id_placeholder = idx
    values.append(transfer_id)

    query = f"""\
        update
            dataset_release_transfer
            set {', '.join(updates)}
            where dataset_release_transfer_id = ${transfer_id_placeholder}
        returning *;
    """

    try:
        async with db.transaction() as conn:
            record = await conn.fetchrow(query, *values)
            if record and payload.transfer_status == "queued":
                await _fan_out_transfer_files(transfer_id, conn)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="updating dataset release transfer", context={"transfer_id": transfer_id})
        api_error("DB_ERROR", "Failed to update transfer", {}, 500)

    if not record:
        api_error("NOT_FOUND", "Dataset release transfer not found", {"transfer_id": transfer_id}, 404)

    return item_response(record)

@router.delete("/transfers/{transfer_id}")
# Delete a dataset release transfer and all its child records
async def delete_dataset_release_transfer(transfer_id: int, db: Database = Depends()):
    async with db.transaction() as conn:
        existing = await conn.fetchrow(
            "select dataset_release_transfer_id from dataset_release_transfer where dataset_release_transfer_id = $1",
            transfer_id,
        )
        if not existing:
            api_error("NOT_FOUND", "Dataset release transfer not found", {"transfer_id": transfer_id}, 404)

        await conn.execute("delete from dataset_release_transfer where dataset_release_transfer_id = $1", transfer_id)

    return {"data": {"deleted": True, "dataset_release_transfer_id": transfer_id}}

# ---------------------------------------- Transfer type-specific fields -----------------------------------------------

@router.get("/transfers/{transfer_id}/idc")
# Get IDC-specific fields for a transfer
async def get_transfer_idc(transfer_id: int, db: Database = Depends()):
    query = """\
        select
            ti.dataset_release_transfer_id,
            ti.base_gcs_url,
            ti.dataset_manifest_file_id,
            df_d.downloadable_file_id  as dataset_manifest_downloadable_file_id,
            df_d.security_hash         as dataset_manifest_security_hash,
            ti.imaging_manifest_file_id,
            df_r.downloadable_file_id  as imaging_manifest_downloadable_file_id,
            df_r.security_hash         as imaging_manifest_security_hash,
            ti.clinical_manifest_file_id,
            df_c.downloadable_file_id  as clinical_manifest_downloadable_file_id,
            df_c.security_hash         as clinical_manifest_security_hash,
            ti.published,
            ti.public
        from transfer_idc ti
        left join downloadable_file df_d on df_d.file_id = ti.dataset_manifest_file_id
        left join downloadable_file df_r on df_r.file_id = ti.imaging_manifest_file_id
        left join downloadable_file df_c on df_c.file_id = ti.clinical_manifest_file_id
        where ti.dataset_release_transfer_id = $1
        """
    try:
        record = await db.fetch(query, [transfer_id])
    except Exception as e:
        db_error(
            e,
            operation="fetching IDC transfer fields",
            context={"transfer_id": transfer_id},
        )

    # Carry which manifests this transfer needs and which are still missing, so
    # the UI can disable Queue rather than let the user discover the 422. Note a
    # transfer with no transfer_idc row yet still reports its requirements.
    manifests = await _idc_manifest_state(transfer_id, db) or {}
    data = {**dict(record[0]), **manifests} if record else {
        "dataset_release_transfer_id": transfer_id, **manifests
    }
    return item_response(data)


@router.put("/transfers/{transfer_id}/idc")
# Upsert IDC-specific fields for a transfer
async def upsert_transfer_idc(
    transfer_id: int,
    payload: TransferIdcUpdate,
    db: Database = Depends()):

    if payload.base_gcs_url is None and payload.published is None and payload.public is None:
        api_error("VALIDATION_ERROR", "No IDC fields were provided", {}, 422)

    query = """\
        insert into transfer_idc (dataset_release_transfer_id, base_gcs_url, published, public)
        values ($1, $2, $3, $4)
        on conflict (dataset_release_transfer_id) do update set
            base_gcs_url = coalesce(excluded.base_gcs_url, transfer_idc.base_gcs_url),
            published    = coalesce(excluded.published,    transfer_idc.published),
            public       = coalesce(excluded.public,       transfer_idc.public)
        returning *
        """
    try:
        record = await db.fetch(query, [transfer_id, payload.base_gcs_url, payload.published, payload.public])
    except Exception as e:
        db_error(
            e,
            operation="upserting IDC transfer fields",
            context={"transfer_id": transfer_id},
        )

    if not record:
        api_error("NOT_FOUND", "Transfer not found", {"transfer_id": transfer_id}, 404)

    return item_response(record[0])


@router.post("/transfers/{transfer_id}/idc/dataset-manifest/generate")
async def generate_idc_dataset_manifest(transfer_id: int, db: Database = Depends()):
    # Resolve transfer → dataset_release → dataset
    rows = await db.fetch(
        """
        select drt.dataset_release_id, dr.dataset_id,
               dr.release_number, dr.release_date
        from dataset_release_transfer drt
        join dataset_release dr using (dataset_release_id)
        where drt.dataset_release_transfer_id = $1
        """,
        [transfer_id],
    )
    if not rows:
        api_error("NOT_FOUND", "Transfer not found", {"transfer_id": transfer_id}, 404)

    dataset_release_id = rows[0]["dataset_release_id"]
    dataset_id         = rows[0]["dataset_id"]
    release_number     = rows[0]["release_number"]
    release_date       = rows[0]["release_date"]

    # Find the WP object mapped to this dataset
    wp_rows = await db.fetch(
        """
        select wp_object_type, wp_object_id
        from wp_object_map
        where posda_object_type = 'dataset' and posda_object_id = $1
        limit 1
        """,
        [dataset_id],
    )
    if not wp_rows:
        api_error("NOT_FOUND", "No WordPress object is mapped to this dataset", {}, 422)

    wp_object_type = wp_rows[0]["wp_object_type"]
    wp_object_id   = wp_rows[0]["wp_object_id"]

    if wp_object_type == "collection":
        wp_endpoint_key = "Collection"
    elif wp_object_type == "analysis_result":
        wp_endpoint_key = "Analysis Result"
    else:
        api_error("VALIDATION_ERROR", f"Unsupported wp_object_type: {wp_object_type}", {}, 400)

    wp_item = await wp_get(f"{wp_url(wp_endpoint_key)}/{wp_object_id}")
    if wp_item is None:
        api_error("NOT_FOUND", f"WordPress {wp_object_type} {wp_object_id} not found", {}, 404)

    def _str(val) -> str:
        if val is None:
            return ""
        if isinstance(val, dict):
            return val.get("rendered") or str(val)
        return str(val)

    def _pipe(val) -> str:
        if val is None:
            return ""
        if isinstance(val, list):
            parts = []
            for v in val:
                if isinstance(v, dict):
                    parts.append(v.get("name") or v.get("slug") or v.get("title") or str(v))
                else:
                    parts.append(str(v))
            return "|".join(parts)
        if isinstance(val, dict):
            return val.get("name") or val.get("slug") or val.get("title") or str(val)
        return str(val)

    if wp_object_type == "collection":
        short_name = _str(wp_item.get("collection_short_title"))
        title      = _str(wp_item.get("collection_title"))
        status     = _str(wp_item.get("collection_status"))
        doi        = _str(wp_item.get("collection_doi"))
        abstract   = _str(wp_item.get("collection_abstract"))
    else:
        short_name = _str(wp_item.get("result_short_title"))
        title      = _str(wp_item.get("result_title"))
        status     = ""
        doi        = _str(wp_item.get("result_doi"))
        abstract   = _str(wp_item.get("result_abstract"))

    citations_raw = wp_item.get("citations")
    if isinstance(citations_raw, list):
        citation = "|".join(
            c.get("tcia_citation_statement") or c.get("tcia_citation_text") or ""
            for c in citations_raw
            if isinstance(c, dict) and c.get("citation_type") == "Data Citation"
        )
    else:
        citation = _str(citations_raw)

    manifest_row = {
        "post_id":              wp_item.get("id", ""),
        "dataset_slug":         _str(wp_item.get("slug")),
        "dataset_type":         _str(wp_item.get("type")),
        "dataset_doi":          doi,
        "dataset_short_name":   short_name,
        "dataset_title":        title,
        "dataset_status":       status,
        # Version and version date describe the release being shipped, so they
        # come from Posda. WordPress isn't updated until dissemination (step 7),
        # which runs after this manifest is generated -- the WP values are stale
        # or absent by construction.
        "dataset_version":      str(release_number),
        "dataset_version_date": release_date.date().isoformat() if release_date else "",
        "dataset_url":          _str(wp_item.get("view_url")),
        "cancer_types":         _pipe(wp_item.get("cancer_types")),
        "supporting_data":      _pipe(wp_item.get("supporting_data")),
        "species":              _pipe(wp_item.get("species")),
        "cancer_locations":     _pipe(wp_item.get("cancer_locations")),
        "program":              _pipe(wp_item.get("program")),
        "abstract":             abstract,
        "citation":             citation,
    }

    # The bucket path anchors every relative path in the imaging and clinical
    # manifests, so derive it here rather than asking someone to type it: this
    # is the one place holding both halves -- the WordPress slug and the release
    # number.
    slug = manifest_row["dataset_slug"]
    base_gcs_url = f"gs://{IDC_TRANSFER_BUCKET}/{slug}/v{release_number}" if slug else None

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(manifest_row.keys()))
    writer.writeheader()
    writer.writerow(manifest_row)
    csv_bytes = buf.getvalue().encode("utf-8")

    digest = hashlib.md5(csv_bytes).hexdigest()
    size   = len(csv_bytes)
    rel_path = os.path.join(digest[:2], digest[2:4], digest[4:6], digest)
    os.makedirs(os.path.join(FILE_STORAGE_PATH, digest[:2], digest[2:4], digest[4:6]), exist_ok=True)
    with open(os.path.join(FILE_STORAGE_PATH, rel_path), "wb") as fh:
        fh.write(csv_bytes)

    security_hash = secrets.token_hex(16)

    try:
        async with db.transaction() as conn:
            file_rows = await conn.fetch(
                """
                insert into file (digest, size, processing_priority)
                values ($1, $2, 1)
                on conflict (digest) do update set digest = excluded.digest
                returning file_id
                """,
                digest, size,
            )
            file_id = file_rows[0]["file_id"]

            await conn.execute(
                """
                insert into file_location (file_id, file_storage_root_id, rel_path)
                values ($1, $2, $3)
                on conflict do nothing
                """,
                file_id, FILE_STORAGE_ROOT, rel_path,
            )

            df_rows = await conn.fetch(
                "select downloadable_file_id, security_hash from downloadable_file where file_id = $1 limit 1",
                file_id,
            )
            if not df_rows:
                df_rows = await conn.fetch(
                    """
                    insert into downloadable_file (file_id, security_hash, mime_type)
                    values ($1, $2, 'text/csv')
                    returning downloadable_file_id, security_hash
                    """,
                    file_id, security_hash,
                )

            await conn.execute(
                """
                insert into transfer_idc (
                    dataset_release_transfer_id, dataset_manifest_file_id, base_gcs_url
                )
                values ($1, $2, $3)
                on conflict (dataset_release_transfer_id) do update
                    set dataset_manifest_file_id = excluded.dataset_manifest_file_id,
                        -- Existing value wins: a relocation edited in the Manage
                        -- modal must survive a manifest regeneration. This only
                        -- ever fills a null.
                        base_gcs_url = coalesce(transfer_idc.base_gcs_url, excluded.base_gcs_url)
                """,
                transfer_id, file_id, base_gcs_url,
            )
    except Exception as e:
        db_error(e, operation="generating IDC dataset manifest", context={"transfer_id": transfer_id})
        api_error("DB_ERROR", "Failed to store manifest", {}, 500)

    return item_response({
        "file_id":               file_id,
        "downloadable_file_id":  df_rows[0]["downloadable_file_id"],
        "security_hash":         df_rows[0]["security_hash"],
    })


@router.post("/transfers/{transfer_id}/idc/imaging-manifest/generate")
async def generate_idc_imaging_manifest(transfer_id: int, db: Database = Depends()):
    # The hash chain (series -> study -> patient -> dataset) is computed over the
    # same rows the CSV is built from, so a DICOM file silently dropped by a
    # missing index row does not merely go missing from the manifest -- it
    # changes the dataset-level hash for the whole submission, and the result
    # still looks internally consistent to IDC. Validate completeness up front
    # and refuse, rather than ship hashes that describe a partial set.
    incomplete_predicate = """
                   fp.file_id is null
                or fst.file_id is null
                or fse.file_id is null
                or fsc.file_id is null
                or coalesce(btrim(fp.patient_id), '') = ''
    """

    preflight_query = f"""
        select
            count(*)                                        as dicom_total,
            count(*) filter (where fp.file_id is null)      as missing_patient_row,
            count(*) filter (where fst.file_id is null)     as missing_study_row,
            count(*) filter (where fse.file_id is null)     as missing_series_row,
            count(*) filter (where fsc.file_id is null)     as missing_sop_row,
            count(*) filter (
                where fp.file_id is not null
                  and coalesce(btrim(fp.patient_id), '') = ''
            )                                               as blank_patient_id,
            count(*) filter (where {incomplete_predicate})  as incomplete_total,
            (array_agg(distinct rrf.file_id)
                filter (where {incomplete_predicate}))[1:20] as sample_file_ids
        from transfer_recordset tr
        join recordset_release rr       using (recordset_release_id)
        join recordset r                using (recordset_id)
        join recordset_type rt          using (recordset_type_id)
        join recordset_release_file rrf using (recordset_release_id)
        join file f                     using (file_id)
        left join file_patient    fp  on fp.file_id  = f.file_id
        left join file_study      fst on fst.file_id = f.file_id
        left join file_series     fse on fse.file_id = f.file_id
        left join file_sop_common fsc on fsc.file_id = f.file_id
        where tr.dataset_release_transfer_id = $1
          and {IDC_IMAGING_PREDICATE}
    """

    try:
        preflight = await db.fetch_one(preflight_query, [transfer_id])
    except HTTPException:
        raise
    except Exception as e:
        db_error(
            e,
            operation="validating files for IDC imaging manifest",
            context={"transfer_id": transfer_id},
        )

    if preflight and preflight["incomplete_total"]:
        api_error(
            "MANIFEST_INCOMPLETE",
            f"{preflight['incomplete_total']} of {preflight['dicom_total']} DICOM files are "
            "missing index data required for the imaging manifest",
            {
                "dicom_file_count":      preflight["dicom_total"],
                "incomplete_file_count": preflight["incomplete_total"],
                "missing_patient_row":   preflight["missing_patient_row"],
                "missing_study_row":     preflight["missing_study_row"],
                "missing_series_row":    preflight["missing_series_row"],
                "missing_sop_row":       preflight["missing_sop_row"],
                "blank_patient_id":      preflight["blank_patient_id"],
                "sample_file_ids":       list(preflight["sample_file_ids"] or []),
            },
            422,
        )

    # DISTINCT: the same file_id can appear in two DICOM recordset releases in
    # one transfer (overlapping recordsets are legal), which would emit duplicate
    # SOP instance rows and feed the digest into string_agg twice, corrupting
    # series_hash and everything above it.
    query = f"""
        WITH files AS (
            SELECT DISTINCT
                rrf.file_id,
                f.digest,
                fp.patient_id,
                fst.study_instance_uid,
                fse.series_instance_uid,
                fsc.sop_instance_uid
            FROM transfer_recordset tr
            JOIN recordset_release rr   USING (recordset_release_id)
            JOIN recordset r            USING (recordset_id)
            JOIN recordset_type rt      USING (recordset_type_id)
            JOIN recordset_release_file rrf USING (recordset_release_id)
            JOIN file f                 USING (file_id)
            JOIN file_patient fp        USING (file_id)
            JOIN file_study fst         USING (file_id)
            JOIN file_series fse        USING (file_id)
            JOIN file_sop_common fsc    USING (file_id)
            WHERE tr.dataset_release_transfer_id = $1
              AND {IDC_IMAGING_PREDICATE}
        ),
        series_hashes AS (
            SELECT series_instance_uid,
                   md5(string_agg(digest, '' ORDER BY digest)) AS series_hash
            FROM files
            GROUP BY series_instance_uid
        ),
        study_hashes AS (
            SELECT sp.study_instance_uid,
                   md5(string_agg(sh.series_hash, '' ORDER BY sh.series_hash)) AS study_hash
            FROM (SELECT DISTINCT study_instance_uid, series_instance_uid FROM files) sp
            JOIN series_hashes sh USING (series_instance_uid)
            GROUP BY sp.study_instance_uid
        ),
        patient_hashes AS (
            SELECT sp.patient_id,
                   md5(string_agg(sh.study_hash, '' ORDER BY sh.study_hash)) AS patient_hash
            FROM (SELECT DISTINCT patient_id, study_instance_uid FROM files) sp
            JOIN study_hashes sh USING (study_instance_uid)
            GROUP BY sp.patient_id
        ),
        dataset_hash AS (
            SELECT md5(string_agg(ph.patient_hash, '' ORDER BY ph.patient_hash)) AS dataset_hash
            FROM (SELECT DISTINCT patient_id FROM files) p
            JOIN patient_hashes ph USING (patient_id)
        )
        SELECT
            dh.dataset_hash,
            f.patient_id,
            ph.patient_hash,
            f.study_instance_uid,
            sth.study_hash,
            f.series_instance_uid,
            sh.series_hash,
            f.sop_instance_uid,
            f.digest AS instance_hash,
            f.file_id
        FROM files f
        JOIN series_hashes sh   USING (series_instance_uid)
        JOIN study_hashes sth   USING (study_instance_uid)
        JOIN patient_hashes ph  USING (patient_id)
        CROSS JOIN dataset_hash dh
        ORDER BY f.patient_id, f.study_instance_uid, f.series_instance_uid, f.sop_instance_uid
    """

    try:
        rows = await db.fetch(query, [transfer_id])
    except Exception as e:
        db_error(e, operation="querying files for IDC imaging manifest", context={"transfer_id": transfer_id})

    if not rows:
        api_error("NOT_FOUND", "No DICOM files found for this transfer", {}, 404)

    fieldnames = [
        "dataset_hash",
        "patient_id", "patient_hash",
        "study_instance_uid", "study_hash",
        "series_instance_uid", "series_hash",
        "sop_instance_uid", "instance_hash", "file_id",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in dict(row).items()})
    csv_bytes = buf.getvalue().encode("utf-8")

    digest = hashlib.md5(csv_bytes).hexdigest()
    size   = len(csv_bytes)
    rel_path = os.path.join(digest[:2], digest[2:4], digest[4:6], digest)
    os.makedirs(os.path.join(FILE_STORAGE_PATH, digest[:2], digest[2:4], digest[4:6]), exist_ok=True)
    with open(os.path.join(FILE_STORAGE_PATH, rel_path), "wb") as fh:
        fh.write(csv_bytes)

    security_hash = secrets.token_hex(16)

    try:
        async with db.transaction() as conn:
            file_rows = await conn.fetch(
                """
                insert into file (digest, size, processing_priority)
                values ($1, $2, 1)
                on conflict (digest) do update set digest = excluded.digest
                returning file_id
                """,
                digest, size,
            )
            file_id = file_rows[0]["file_id"]

            await conn.execute(
                """
                insert into file_location (file_id, file_storage_root_id, rel_path)
                values ($1, $2, $3)
                on conflict do nothing
                """,
                file_id, FILE_STORAGE_ROOT, rel_path,
            )

            df_rows = await conn.fetch(
                "select downloadable_file_id, security_hash from downloadable_file where file_id = $1 limit 1",
                file_id,
            )
            if not df_rows:
                df_rows = await conn.fetch(
                    """
                    insert into downloadable_file (file_id, security_hash, mime_type)
                    values ($1, $2, 'text/csv')
                    returning downloadable_file_id, security_hash
                    """,
                    file_id, security_hash,
                )

            await conn.execute(
                """
                insert into transfer_idc (dataset_release_transfer_id, imaging_manifest_file_id)
                values ($1, $2)
                on conflict (dataset_release_transfer_id) do update
                    set imaging_manifest_file_id = excluded.imaging_manifest_file_id
                """,
                transfer_id, file_id,
            )
    except Exception as e:
        db_error(e, operation="storing IDC imaging manifest", context={"transfer_id": transfer_id})

    return item_response({
        "file_id":              file_id,
        "downloadable_file_id": df_rows[0]["downloadable_file_id"],
        "security_hash":        df_rows[0]["security_hash"],
        "row_count":            len(rows),
        "dataset_hash":         rows[0]["dataset_hash"],
    })


async def _fan_out_transfer_files(transfer_id: int, conn) -> None:
    """Materialize one transfer_file row per file the transfer will upload.

    Called at the queue transition, in the same transaction as the status flip:
    the daemon treats a queued transfer with no completed files as failed, so a
    crash between the two would look like a real failure rather than a retry.

    Paths are stored **relative** to transfer_idc.base_gcs_url, which the daemon
    joins them to. That keeps relocating a package a single-field edit instead of
    a rewrite of every row, and makes file_dest_url the same string the manifests
    carry in relative_file_url, so the two cannot drift.

    IDC only -- no other destination has a path scheme or a daemon yet. Files
    matching neither predicate are skipped rather than uploaded: IDC cannot
    interpret an object with no manifest row, and the upload cannot be recalled.
    _idc_manifest_state reports them so they are skipped visibly, not silently.
    """
    await conn.execute(
        f"""
        insert into transfer_file (
            dataset_release_transfer_id, file_id, file_dest_url, status
        )
        select distinct
            $1,
            rrf.file_id,
            case when {IDC_IMAGING_PREDICATE}
                 -- Content-addressed, which is what makes the daemon's
                 -- HEAD-then-verify-MD5 re-runs idempotent.
                 then 'imaging/'  || f.digest
                 -- Same expression the clinical manifest uses for its file name,
                 -- fallback included -- file_name is null for most rows.
                 else 'clinical/' || coalesce(rrf.file_name, rrf.file_id::text)
            end,
            'pending'
        from dataset_release_transfer drt
        join transfer_destination td    using (destination_id)
        join transfer_recordset tr      using (dataset_release_transfer_id)
        join recordset_release rr       using (recordset_release_id)
        join recordset rs               using (recordset_id)
        join recordset_type rt          using (recordset_type_id)
        join recordset_release_file rrf on rrf.recordset_release_id = tr.recordset_release_id
        join file f                     on f.file_id = rrf.file_id
        where drt.dataset_release_transfer_id = $1
          and td.destination_abbr = 'idc'
          and ({IDC_IMAGING_PREDICATE} or {IDC_CLINICAL_PREDICATE})
        -- Re-runnable: a re-queue keeps the rows already there, so the daemon's
        -- own failed -> pending reset decides what gets retried.
        on conflict (dataset_release_transfer_id, file_id) do nothing
        """,
        transfer_id,
    )


async def _idc_manifest_state(transfer_id: int, db: Database):
    """Which IDC manifests this transfer needs, and which are missing.

    Required is derived from what the transfer actually carries, not a fixed
    list: the dataset manifest always (it identifies the submission), the
    imaging manifest when it carries DICOM, the clinical manifest when it
    carries files from a Clinical Data recordset. A transfer with no clinical
    content does not need a clinical manifest -- absence is the signal that
    nothing clinical changed.

    Also reports files matching neither predicate. Those are skipped by the
    fan-out rather than uploaded, since IDC cannot interpret an object with no
    manifest row and the upload cannot be recalled -- so they are surfaced here
    for whoever is queueing to see.

    Returns None for a non-IDC transfer, which has no transfer-level manifests.
    """
    destination = await db.fetch_one(
        """
        select td.destination_abbr
        from dataset_release_transfer drt
        join transfer_destination td using (destination_id)
        where drt.dataset_release_transfer_id = $1
        """,
        [transfer_id],
    )
    if not destination or destination["destination_abbr"] != "idc":
        return None

    content = await db.fetch_one(
        f"""
        select
            count(*) filter (where {IDC_IMAGING_PREDICATE})  as imaging_files,
            count(*) filter (where {IDC_CLINICAL_PREDICATE}) as clinical_files,
            count(*) filter (
                where not ({IDC_IMAGING_PREDICATE})
                  and not ({IDC_CLINICAL_PREDICATE})
            ) as unlistable_files,
            array_agg(distinct rs.recordset_name) filter (
                where not ({IDC_IMAGING_PREDICATE})
                  and not ({IDC_CLINICAL_PREDICATE})
            ) as unlistable_recordsets
        from transfer_recordset tr
        join recordset_release rr       using (recordset_release_id)
        join recordset rs               using (recordset_id)
        join recordset_type rt          using (recordset_type_id)
        join recordset_release_file rrf using (recordset_release_id)
        join file f                     using (file_id)
        where tr.dataset_release_transfer_id = $1
        """,
        [transfer_id],
    )

    required = ["dataset"]
    if content and content["imaging_files"]:
        required.append("imaging")
    if content and content["clinical_files"]:
        required.append("clinical")

    existing = await db.fetch_one(
        """
        select dataset_manifest_file_id, imaging_manifest_file_id,
               clinical_manifest_file_id
        from transfer_idc
        where dataset_release_transfer_id = $1
        """,
        [transfer_id],
    )

    missing = [
        name
        for name in required
        if not existing or existing[f"{name}_manifest_file_id"] is None
    ]
    return {
        "required_manifests": required,
        "missing_manifests": missing,
        "unlistable_files": (content["unlistable_files"] if content else 0) or 0,
        "unlistable_recordsets": list(
            (content["unlistable_recordsets"] if content else None) or []
        ),
    }


async def _wp_precedence_block(transfer_id: int, db: Database):
    """Why an IDC transfer must wait for the WordPress transfer, or None.

    Clinical files reach IDC as *links into Collection Manager*, not as copies:
    the manifest's `download_url` points at CM. So if Posda's clinical file is an
    update of what CM currently holds and IDC pulls first, the manifest resolves
    to the **previous** file while looking entirely valid -- nothing downstream
    can tell. Checking that CM merely has a file attached is not enough for the
    same reason: the stale one is attached too.

    So the gate is the WordPress transfer for this same dataset release having
    delivered. WordPress is the `default_display` destination for these
    recordsets -- it takes precedence, and IDC follows it.

    Only applies to clinical content whose primary destination is WordPress; an
    IDC transfer carrying no such files has no dependency and is not gated.

    Scoped to IDC transfers. Other destinations carry their own copy of the file
    rather than linking to CM, so they have no such ordering -- and without this
    guard the WordPress transfer would block on itself, making the gate
    impossible to ever satisfy.
    """
    destination = await db.fetch_one(
        """
        select td.destination_abbr
        from dataset_release_transfer drt
        join transfer_destination td using (destination_id)
        where drt.dataset_release_transfer_id = $1
        """,
        [transfer_id],
    )
    if not destination or destination["destination_abbr"] != "idc":
        return None

    blocking_recordsets = await db.fetch(
        f"""
        select distinct rs.recordset_id, rs.recordset_name
        from transfer_recordset tr
        join recordset_release rr       using (recordset_release_id)
        join recordset rs               using (recordset_id)
        join recordset_type rt          using (recordset_type_id)
        join recordset_release_file rrf using (recordset_release_id)
        join file f                     using (file_id)
        join recordset_destination rd   on rd.recordset_id = rs.recordset_id
        join transfer_destination td    on td.destination_id = rd.destination_id
        where tr.dataset_release_transfer_id = $1
          and {IDC_CLINICAL_PREDICATE}
          and rd.default_display
          and td.destination_abbr = 'wp'
        order by rs.recordset_name
        """,
        [transfer_id],
    )
    if not blocking_recordsets:
        return None

    wp_transfer = await db.fetch_one(
        """
        select wp.transfer_status
        from dataset_release_transfer drt
        join dataset_release_transfer wp
             on wp.dataset_release_id = drt.dataset_release_id
        join transfer_destination td
             on td.destination_id = wp.destination_id
        where drt.dataset_release_transfer_id = $1
          and td.destination_abbr = 'wp'
        """,
        [transfer_id],
    )

    status = wp_transfer["transfer_status"] if wp_transfer else None
    if status == "success":
        return None

    return {
        "wp_transfer_status": status,
        "recordsets": [r["recordset_name"] for r in blocking_recordsets],
    }


def _cm_value(item: dict, key: str) -> str:
    """One Collection Manager field as a CSV cell. Some (download_type) come back
    as lists; flatten rather than emitting a Python repr."""
    value = item.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


@router.post("/transfers/{transfer_id}/idc/clinical-manifest/generate")
async def generate_idc_clinical_manifest(transfer_id: int, db: Database = Depends()):
    # "Clinical" here means the non-DICOM tabular supporting data this transfer
    # carries. Sourced from Posda, not a live Collection Manager read: by the
    # time a transfer runs the files have already been pulled into Posda and
    # QC'd, so the recordsets are the record of both what ships and where.
    #
    # `is_dicom_file is not true` rather than `= false` -- the column is
    # nullable, and `= false` would silently skip an unprocessed file. Nothing
    # filters on file.file_type: Posda stores a libmagic description there
    # ("ASCII text, with CRLF line terminators"), which cannot tell CSV from
    # anything else. Per-recordset destination assignment is the selection
    # mechanism, so everything non-DICOM in the transfer is listed.
    files_query = f"""
        select
            rs.recordset_id,
            rs.recordset_name,
            rrf.file_name,
            f.file_id,
            f.digest,
            f.size
        from transfer_recordset tr
        join recordset_release rr       using (recordset_release_id)
        join recordset rs               using (recordset_id)
        join recordset_type rt          using (recordset_type_id)
        join recordset_release_file rrf using (recordset_release_id)
        join file f                     using (file_id)
        where tr.dataset_release_transfer_id = $1
          and {IDC_CLINICAL_PREDICATE}
        order by rs.recordset_name, rrf.file_name
        """

    try:
        rows = await db.fetch(files_query, [transfer_id])
    except Exception as e:
        db_error(
            e,
            operation="querying files for IDC clinical manifest",
            context={"transfer_id": transfer_id},
        )

    # An absent manifest means "nothing clinical in this release" -- a real
    # state, not something to paper over with an empty CSV.
    if not rows:
        api_error(
            "NOT_FOUND",
            "No clinical (non-DICOM) files found for this transfer",
            {"transfer_id": transfer_id},
            404,
        )

    blocked = await _wp_precedence_block(transfer_id, db)
    if blocked:
        api_error(
            "WP_TRANSFER_REQUIRED",
            "The WordPress transfer for this release has not delivered yet, so "
            "Collection Manager may still hold the previous version of these "
            "clinical files. Ship to WordPress first.",
            {"transfer_id": transfer_id, **blocked},
            422,
        )

    # wp_object_map is unique both ways, so a recordset maps to at most one CM
    # download -- fetch each once rather than per file. Best effort: CM may not
    # be live when a transfer is prepared, and every CM column is optional, so a
    # failed lookup leaves those cells blank. Failures are reported in the
    # response rather than swallowed.
    recordset_ids = sorted({r["recordset_id"] for r in rows})
    link_rows = await db.fetch(
        """
        select posda_object_id as recordset_id, wp_object_id
        from wp_object_map
        where posda_object_type = 'recordset'
          and wp_object_type = 'download'
          and posda_object_id = any($1::int[])
        """,
        [recordset_ids],
    )

    wp_by_recordset = {}
    wp_lookup_failures = []
    for link in link_rows:
        try:
            item = await wp_get(f"{wp_url('Download')}/{link['wp_object_id']}")
        except Exception:
            item = None
        if item:
            wp_by_recordset[link["recordset_id"]] = item
        else:
            wp_lookup_failures.append(link["wp_object_id"])

    fieldnames = [
        "download_slug", "download_id", "date_updated", "download_title",
        "file_type", "file_name", "download_size", "download_size_unit",
        "download_url", "download_type", "file_hash", "relative_file_url",
        "posda_file_id",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        wp = wp_by_recordset.get(r["recordset_id"]) or {}
        name = r["file_name"] or str(r["file_id"])
        extension = name.rsplit(".", 1)[-1].upper() if "." in name else ""
        writer.writerow({
            "download_slug":      _cm_value(wp, "slug"),
            "download_id":        _cm_value(wp, "id"),
            "date_updated":       _cm_value(wp, "date_updated"),
            "download_title":     _cm_value(wp, "download_title"),
            # CM keeps its own file_type list; Posda's file.file_type is a
            # libmagic string, so the extension is the closest honest answer.
            "file_type":          extension,
            "file_name":          name,
            "download_size":      "" if r["size"] is None else r["size"],
            "download_size_unit": "" if r["size"] is None else "B",
            "download_url":       _cm_value(wp, "download_url"),
            "download_type":      _cm_value(wp, "download_type"),
            "file_hash":          r["digest"] or "",
            # Same relative scheme as the imaging manifest: clinical files land
            # in the version folder's clinical/ subfolder.
            "relative_file_url":  f"./clinical/{name}",
            "posda_file_id":      r["file_id"],
        })
    csv_bytes = buf.getvalue().encode("utf-8")

    digest = hashlib.md5(csv_bytes).hexdigest()
    size   = len(csv_bytes)
    rel_path = os.path.join(digest[:2], digest[2:4], digest[4:6], digest)
    os.makedirs(os.path.join(FILE_STORAGE_PATH, digest[:2], digest[2:4], digest[4:6]), exist_ok=True)
    with open(os.path.join(FILE_STORAGE_PATH, rel_path), "wb") as fh:
        fh.write(csv_bytes)

    security_hash = secrets.token_hex(16)

    try:
        async with db.transaction() as conn:
            file_rows = await conn.fetch(
                """
                insert into file (digest, size, processing_priority)
                values ($1, $2, 1)
                on conflict (digest) do update set digest = excluded.digest
                returning file_id
                """,
                digest, size,
            )
            file_id = file_rows[0]["file_id"]

            await conn.execute(
                """
                insert into file_location (file_id, file_storage_root_id, rel_path)
                values ($1, $2, $3)
                on conflict do nothing
                """,
                file_id, FILE_STORAGE_ROOT, rel_path,
            )

            df_rows = await conn.fetch(
                "select downloadable_file_id, security_hash from downloadable_file where file_id = $1 limit 1",
                file_id,
            )
            if not df_rows:
                df_rows = await conn.fetch(
                    """
                    insert into downloadable_file (file_id, security_hash, mime_type)
                    values ($1, $2, 'text/csv')
                    returning downloadable_file_id, security_hash
                    """,
                    file_id, security_hash,
                )

            await conn.execute(
                """
                insert into transfer_idc (dataset_release_transfer_id, clinical_manifest_file_id)
                values ($1, $2)
                on conflict (dataset_release_transfer_id) do update
                    set clinical_manifest_file_id = excluded.clinical_manifest_file_id
                """,
                transfer_id, file_id,
            )
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="storing IDC clinical manifest", context={"transfer_id": transfer_id})

    return item_response({
        "file_id":              file_id,
        "downloadable_file_id": df_rows[0]["downloadable_file_id"],
        "security_hash":        df_rows[0]["security_hash"],
        "row_count":            len(rows),
        "wp_lookup_failures":   wp_lookup_failures,
    })


@router.get("/transfers/{transfer_id}/gc")
async def get_transfer_gc(transfer_id: int, db: Database = Depends()):
    query = """\
        select dataset_release_transfer_id, published, public
        from transfer_gc
        where dataset_release_transfer_id = $1
        """
    try:
        record = await db.fetch(query, [transfer_id])
    except Exception as e:
        db_error(e, operation="fetching GC transfer fields", context={"transfer_id": transfer_id})
    return item_response(record[0] if record else None)


@router.put("/transfers/{transfer_id}/gc")
async def upsert_transfer_gc(transfer_id: int, payload: TransferGcUpdate, db: Database = Depends()):
    if payload.published is None and payload.public is None:
        api_error("VALIDATION_ERROR", "No GC fields were provided", {}, 422)
    query = """\
        insert into transfer_gc (dataset_release_transfer_id, published, public)
        values ($1, $2, $3)
        on conflict (dataset_release_transfer_id) do update set
            published = coalesce(excluded.published, transfer_gc.published),
            public    = coalesce(excluded.public,    transfer_gc.public)
        returning *
        """
    try:
        record = await db.fetch(query, [transfer_id, payload.published, payload.public])
    except Exception as e:
        db_error(e, operation="upserting GC transfer fields", context={"transfer_id": transfer_id})
    if not record:
        api_error("NOT_FOUND", "Transfer not found", {"transfer_id": transfer_id}, 404)
    return item_response(record[0])


@router.get("/transfers/{transfer_id}/aspera")
async def get_transfer_aspera(transfer_id: int, db: Database = Depends()):
    query = """\
        select dataset_release_transfer_id, published, public, faspex_url
        from transfer_aspera
        where dataset_release_transfer_id = $1
        """
    try:
        record = await db.fetch(query, [transfer_id])
    except Exception as e:
        db_error(e, operation="fetching Aspera transfer fields", context={"transfer_id": transfer_id})
    return item_response(record[0] if record else None)


@router.put("/transfers/{transfer_id}/aspera")
async def upsert_transfer_aspera(transfer_id: int, payload: TransferAsperaUpdate, db: Database = Depends()):
    if payload.published is None and payload.public is None and payload.faspex_url is None:
        api_error("VALIDATION_ERROR", "No Aspera fields were provided", {}, 422)
    query = """\
        insert into transfer_aspera (dataset_release_transfer_id, published, public, faspex_url)
        values ($1, $2, $3, $4)
        on conflict (dataset_release_transfer_id) do update set
            published  = coalesce(excluded.published,  transfer_aspera.published),
            public     = coalesce(excluded.public,     transfer_aspera.public),
            faspex_url = coalesce(excluded.faspex_url, transfer_aspera.faspex_url)
        returning *
        """
    try:
        record = await db.fetch(query, [transfer_id, payload.published, payload.public, payload.faspex_url])
    except Exception as e:
        db_error(e, operation="upserting Aspera transfer fields", context={"transfer_id": transfer_id})
    if not record:
        api_error("NOT_FOUND", "Transfer not found", {"transfer_id": transfer_id}, 404)
    return item_response(record[0])


@router.get("/transfers/{transfer_id}/nbia")
async def get_transfer_nbia(transfer_id: int, db: Database = Depends()):
    query = """\
        select dataset_release_transfer_id, collection, site, published, public
        from transfer_nbia
        where dataset_release_transfer_id = $1
        """
    try:
        record = await db.fetch(query, [transfer_id])
    except Exception as e:
        db_error(e, operation="fetching NBIA transfer fields", context={"transfer_id": transfer_id})
    return item_response(record[0] if record else None)


@router.put("/transfers/{transfer_id}/nbia")
async def upsert_transfer_nbia(transfer_id: int, payload: TransferNbiaUpdate, db: Database = Depends()):
    if payload.collection is None and payload.site is None and payload.published is None and payload.public is None:
        api_error("VALIDATION_ERROR", "No NBIA fields were provided", {}, 422)
    query = """\
        insert into transfer_nbia (dataset_release_transfer_id, collection, site, published, public)
        values ($1, $2, $3, $4, $5)
        on conflict (dataset_release_transfer_id) do update set
            collection = coalesce(excluded.collection, transfer_nbia.collection),
            site       = coalesce(excluded.site,       transfer_nbia.site),
            published  = coalesce(excluded.published,  transfer_nbia.published),
            public     = coalesce(excluded.public,     transfer_nbia.public)
        returning *
        """
    try:
        record = await db.fetch(query, [transfer_id, payload.collection, payload.site, payload.published, payload.public])
    except Exception as e:
        db_error(e, operation="upserting NBIA transfer fields", context={"transfer_id": transfer_id})
    if not record:
        api_error("NOT_FOUND", "Transfer not found", {"transfer_id": transfer_id}, 404)
    return item_response(record[0])


@router.get("/transfers/{transfer_id}/wp")
async def get_transfer_wp(transfer_id: int, db: Database = Depends()):
    query = """\
        select dataset_release_transfer_id, wp_media_file_id, published, public
        from transfer_wp
        where dataset_release_transfer_id = $1
        """
    try:
        record = await db.fetch(query, [transfer_id])
    except Exception as e:
        db_error(e, operation="fetching WordPress transfer fields", context={"transfer_id": transfer_id})
    return item_response(record[0] if record else None)


@router.put("/transfers/{transfer_id}/wp")
async def upsert_transfer_wp(transfer_id: int, payload: TransferWpUpdate, db: Database = Depends()):
    if payload.wp_media_file_id is None and payload.published is None and payload.public is None:
        api_error("VALIDATION_ERROR", "No WordPress fields were provided", {}, 422)
    query = """\
        insert into transfer_wp (dataset_release_transfer_id, wp_media_file_id, published, public)
        values ($1, $2, $3, $4)
        on conflict (dataset_release_transfer_id) do update set
            wp_media_file_id = coalesce(excluded.wp_media_file_id, transfer_wp.wp_media_file_id),
            published        = coalesce(excluded.published,        transfer_wp.published),
            public           = coalesce(excluded.public,           transfer_wp.public)
        returning *
        """
    try:
        record = await db.fetch(query, [transfer_id, payload.wp_media_file_id, payload.published, payload.public])
    except Exception as e:
        db_error(e, operation="upserting WordPress transfer fields", context={"transfer_id": transfer_id})
    if not record:
        api_error("NOT_FOUND", "Transfer not found", {"transfer_id": transfer_id}, 404)
    return item_response(record[0])


# ---------------------------------------- Transfer recordset membership-----------------------------------------------

@router.get("/transfers/{transfer_id}/recordsets")
# List recordset releases included in a transfer
async def get_recordset_releases_by_transfer(transfer_id: int, db: Database = Depends()):
    query = """\
        select
          rr.recordset_release_id,
          r.recordset_id,
          r.recordset_name,
          rr.release_number,
          tr.retriever_manifest_file_id,
          df.downloadable_file_id,
          df.security_hash,
          rt.recordset_type_name
        from
            transfer_recordset tr
            join recordset_release rr on tr.recordset_release_id = rr.recordset_release_id
            join recordset r on rr.recordset_id = r.recordset_id
            join recordset_type rt on r.recordset_type_id = rt.recordset_type_id
            left join downloadable_file df on df.file_id = tr.retriever_manifest_file_id
        where
            tr.dataset_release_transfer_id = $1
        order by r.recordset_name, rr.release_number;
        """
    try:
        records = await db.fetch(query, [transfer_id])
        return list_response(records)
    except Exception as e:
        db_error(
            e,
            operation="fetching recordset releases",
            context={"transfer_id": transfer_id},
        )
        return list_response([])

@router.post("/transfers/{transfer_id}/recordsets/{recordset_release_id}/manifest/generate")
# Generate (or replace) an IDC download manifest CSV for a transfer recordset
async def generate_transfer_recordset_manifest(
    transfer_id: int,
    recordset_release_id: int,
    db: Database = Depends(),
):
    # Verify the transfer_recordset row exists
    tr_row = await db.fetch(
        "select 1 from transfer_recordset "
        "where dataset_release_transfer_id = $1 and recordset_release_id = $2",
        [transfer_id, recordset_release_id],
    )
    if not tr_row:
        api_error("NOT_FOUND", "Transfer recordset not found", {"transfer_id": transfer_id, "recordset_release_id": recordset_release_id}, 404)

    # Get series_instance_uids for this recordset release
    series_rows = await db.fetch(
        """
        select distinct fse.series_instance_uid
        from recordset_release_file rrf
        join file_series fse using (file_id)
        where rrf.recordset_release_id = $1
        order by fse.series_instance_uid
        """,
        [recordset_release_id],
    )

    # Build CSV: header + one UID per line
    lines = ["series_instance_uid"] + [r["series_instance_uid"] for r in series_rows]
    csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")

    # Content-addressed storage: md5 hex digest as filename
    digest = hashlib.md5(csv_bytes).hexdigest()
    size = len(csv_bytes)
    rel_path = os.path.join(digest[:2], digest[2:4], digest[4:6], digest)
    full_dir = os.path.join(FILE_STORAGE_PATH, digest[:2], digest[2:4], digest[4:6])
    os.makedirs(full_dir, exist_ok=True)
    with open(os.path.join(FILE_STORAGE_PATH, rel_path), "wb") as fh:
        fh.write(csv_bytes)

    security_hash = secrets.token_hex(16)

    try:
        async with db.transaction() as conn:
            # Upsert file record
            file_rows = await conn.fetch(
                """
                insert into file (digest, size, processing_priority)
                values ($1, $2, 1)
                on conflict (digest) do update set digest = excluded.digest
                returning file_id
                """,
                digest, size,
            )
            file_id = file_rows[0]["file_id"]

            # Register file location (no-op if already exists)
            await conn.execute(
                """
                insert into file_location (file_id, file_storage_root_id, rel_path)
                values ($1, $2, $3)
                on conflict do nothing
                """,
                file_id, FILE_STORAGE_ROOT, rel_path,
            )

            # Reuse existing downloadable_file if one already exists for this file_id,
            # otherwise create a new one (handles content-identical regenerations)
            df_rows = await conn.fetch(
                "select downloadable_file_id, security_hash from downloadable_file where file_id = $1 limit 1",
                file_id,
            )
            if not df_rows:
                df_rows = await conn.fetch(
                    """
                    insert into downloadable_file (file_id, security_hash, mime_type)
                    values ($1, $2, 'text/csv')
                    returning downloadable_file_id, security_hash
                    """,
                    file_id, security_hash,
                )

            # Link manifest back to transfer_recordset
            await conn.execute(
                """
                update transfer_recordset
                set retriever_manifest_file_id = $1
                where dataset_release_transfer_id = $2 and recordset_release_id = $3
                """,
                file_id, transfer_id, recordset_release_id,
            )
    except Exception as e:
        db_error(e, operation="generating transfer recordset manifest", context={"transfer_id": transfer_id, "recordset_release_id": recordset_release_id})
        api_error("DB_ERROR", "Failed to store manifest", {}, 500)

    return item_response({
        "file_id": file_id,
        "downloadable_file_id": df_rows[0]["downloadable_file_id"],
        "security_hash": df_rows[0]["security_hash"],
        "series_count": len(series_rows),
    })

# NOTE:
# AI tools suggest that this is not optimal
# it mentions something about using a batched option
# which would look something like "insert into ... select unnest($2::int[])"
# I have left this out for consistentcy and readability, our other endpoints aren't using it
# If we expect a very large number of adds and removes it may be worth considering such optimizations
@router.post("/transfers/{transfer_id}/recordsets/add")
# Add recordset releases to a transfer
async def add_recordset_release_to_transfer(
    transfer_id: int,
    payload: TransferReleaseRecordsetRequest,
    db: Database = Depends()):

    insert_query = """
            insert into transfer_recordset
            (dataset_release_transfer_id, recordset_release_id)
            values ($1, $2)
            returning recordset_release_id
        """
    count_query = """
            select count(*) as current_count
            from transfer_recordset
            where dataset_release_transfer_id = $1
        """

    recordset_release_ids = payload.recordset_release_ids

    if not recordset_release_ids:
        return api_error(
            "VALIDATION_ERROR",
            "No records to insert",
            {"recordset_release_ids": []},
            422,
        )

    added_recordset_release_ids = []
    count_record = []

    try:
        for recordset_release_id in recordset_release_ids:
            record = await db.fetch(insert_query, [transfer_id, recordset_release_id])
            if record:
                added_recordset_release_ids.append(record[0]["recordset_release_id"])

        count_record = await db.fetch(count_query, [transfer_id])
    except Exception as e:
        db_error(
            e,
            operation="adding recordset releases to transfer",
            context={"transfer_id": transfer_id},
        )

    return item_response(
        {
            "dataset_transfer_id": transfer_id,
            "added_recordset_release_ids": added_recordset_release_ids,
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


@router.post("/transfers/{transfer_id}/recordsets/remove")
# Remove recordset releases from a transfer
async def remove_recordset_release_from_transfer(
    transfer_id: int,
    payload: TransferReleaseRecordsetRequest,
    db: Database = Depends()):

    delete_query = """
            delete from transfer_recordset
            where dataset_release_transfer_id = $1 and recordset_release_id = $2
            returning recordset_release_id
        """
    count_query = """
            select count(*) as current_count
            from transfer_recordset
            where dataset_release_transfer_id = $1
        """

    recordset_release_ids = payload.recordset_release_ids

    if not recordset_release_ids:
        return api_error(
            "VALIDATION_ERROR",
            "No records to remove",
            {"recordset_release_ids": []},
            422,
        )

    removed_recordset_release_ids = []
    count_record = []

    try:
        for recordset_release_id in recordset_release_ids:
            record = await db.fetch(delete_query, [transfer_id, recordset_release_id])
            if record:
                removed_recordset_release_ids.append(record[0]["recordset_release_id"])

        count_record = await db.fetch(count_query, [transfer_id])
    except Exception as e:
        db_error(
            e,
            operation="removing recordset releases from dataset release",
            context={"transfer_id": transfer_id},
        )

    return item_response(
        {
            "dataset_transfer_id": transfer_id,
            "removed_recordset_release_ids": removed_recordset_release_ids,
            "current_count": count_record[0]["current_count"] if count_record else 0,
        }
    )


# =====================================================================================
# QC REVIEWS / ASSIGNMENTS / FLAGS
# =====================================================================================

# --- QC Models ---

class QCReviewCreate(BaseModel):
    review_type: str                                # 'full' | 'partial' | 'non_dicom'
    sample_percentage: Optional[float] = None       # required when partial
    sample_seed: Optional[int] = None               # server-generated when omitted
    review_notes: Optional[str] = None
    assign_to_caller: bool = False                  # claim the initial slice for the caller

class QCReviewUpdate(BaseModel):
    review_status: Optional[str] = None             # open | complete | cancelled
    review_notes: Optional[str] = None

class QCReviewClone(BaseModel):
    mode: Optional[str] = "carry_forward"           # carry_forward | resample
    review_notes: Optional[str] = None

class QCSplitRequest(BaseModel):
    user_ids: Optional[list[int]] = None            # one assigned slice per user
    count: Optional[int] = None                     # N unclaimed pickup slices
    force: bool = False

class QCAssignmentUpdate(BaseModel):
    assigned_to: Optional[int] = None
    assignment_status: Optional[str] = None

class QCSeriesStatusUpdate(BaseModel):
    qc_status: str
    notes: Optional[str] = None

class QCSeriesBatchStatus(BaseModel):
    series_instance_uids: list[str]
    qc_status: str
    notes: Optional[str] = None

class UserFlagCreate(BaseModel):
    object_type: str
    object_id: int
    series_instance_uid: Optional[str] = None
    flagged_for: int
    note: Optional[str] = None

class UserFlagUpdate(BaseModel):
    flag_status: Optional[str] = None
    note: Optional[str] = None
    flagged_for: Optional[int] = None


VALID_QC_STATUS = ("pending", "approved", "rejected", "flagged")
VALID_REVIEW_STATUS = ("open", "complete", "cancelled")

# Shared draw: a draft's series population + deterministic per-modality sample rank.
#   $1 = recordset_draft_id, $2 = seed (text)
# Selection predicate (full or ceil sample): ($3 = true or rn <= ceil($4::numeric/100*mcount))
QC_DRAW_CTE = """
        pop as (
            select fs.series_instance_uid as suid,
                   max(fs.modality) as modality,
                   md5(string_agg(f.digest, '' order by f.digest)) as series_file_hash
            from recordset_draft_file rdf
            join file_series fs on fs.file_id = rdf.file_id
            join file f on f.file_id = rdf.file_id
            where rdf.recordset_draft_id = $1
            group by fs.series_instance_uid
        ),
        drawn as (
            select suid, modality, series_file_hash,
                   row_number() over (partition by modality order by md5($2 || suid)) as rn,
                   count(*) over (partition by modality) as mcount
            from pop
        )
"""


def paged_response(rows, total, page=None, limit=None):
    meta = {"count": len(rows), "total": total}
    if page is not None and limit is not None:
        meta["page"] = page
        meta["limit"] = limit
    return {"data": rows, "meta": meta}


def page_clause(page: Optional[int], limit: Optional[int]):
    if page is None or limit is None:
        return ""
    p = page if page and page > 0 else 1
    l = limit if limit and limit > 0 else 1
    return f"limit {int(l)} offset {int((p - 1) * l)}"


async def qc_sync_assignment_status(conn, assignment_id: int):
    # Auto: a slice completes when it has 0 pending series; reverts if pending reappears.
    counts = await conn.fetch(
        "select count(*) as total, count(*) filter (where qc_status = 'pending') as pending "
        "from qc_unit where assignment_id = $1",
        assignment_id,
    )
    total = counts[0]["total"]
    pending = counts[0]["pending"]
    if total > 0 and pending == 0:
        await conn.execute(
            "update qc_review_assignment set assignment_status = 'complete', when_updated = now() "
            "where assignment_id = $1 and assignment_status <> 'complete'",
            assignment_id,
        )
    else:
        await conn.execute(
            "update qc_review_assignment set assignment_status = 'in_progress', when_updated = now() "
            "where assignment_id = $1 and assignment_status = 'complete'",
            assignment_id,
        )


async def qc_approve_all_units(conn, assignment_id: int, user_id: int, note: str) -> int:
    # Approve every not-yet-approved unit in a slice (history per unit) and let
    # qc_sync flip the slice to complete. Shared by the non-DICOM Mark-Approved
    # action and the Bundle-testing shortcut. Returns the count approved.
    rows = await conn.fetch(
        "select qc_unit_id, qc_status from qc_unit "
        "where assignment_id = $1 and qc_status <> 'approved'",
        assignment_id,
    )
    for r in rows:
        await conn.execute(
            "update qc_unit set qc_status = 'approved' where qc_unit_id = $1", r["qc_unit_id"])
        await conn.execute(
            "insert into qc_unit_history (qc_unit_id, previous_status, new_status, who_updated, notes) "
            "values ($1, $2, 'approved', $3, $4)",
            r["qc_unit_id"], r["qc_status"], user_id, note)
    await qc_sync_assignment_status(conn, assignment_id)
    return len(rows)


def qc_modality_summary(pop_rows, samp_rows):
    pop = {r["modality"]: r["population_count"] for r in pop_rows}
    samp = {r["modality"]: r["sampled_count"] for r in samp_rows}
    return [
        {
            "modality": m,
            "population_count": pop[m],
            "sampled_count": samp.get(m, 0),
        }
        for m in pop
    ]


QC_POP_PER_MOD = """
    select coalesce(modality, '(none)') as modality, count(*) as population_count
    from (
        select fs.series_instance_uid as suid, max(fs.modality) as modality
        from recordset_draft_file rdf
        join file_series fs on fs.file_id = rdf.file_id
        where rdf.recordset_draft_id = $1
        group by fs.series_instance_uid
    ) p
    group by coalesce(modality, '(none)')
"""

QC_SAMPLED_PER_MOD = """
    select coalesce(modality, '(none)') as modality, count(*) as sampled_count
    from qc_unit where qc_review_id = $1
    group by coalesce(modality, '(none)')
"""


# ------------------------------------- QC REVIEWS -------------------------------------

@router.post("/recordsets/drafts/{draft_id}/qc-reviews")
# Create a QC review (full or partial sample) + its initial assignment + sampled series
async def create_qc_review(
    draft_id: int,
    payload: QCReviewCreate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    review_type = payload.review_type
    if review_type not in ("full", "partial", "non_dicom"):
        api_error("VALIDATION_ERROR", "review_type must be 'full', 'partial', or 'non_dicom'",
                  {"review_type": review_type}, 422)

    is_non_dicom = review_type == "non_dicom"
    is_full = review_type == "full"
    pct = None
    if review_type == "partial":
        pct = payload.sample_percentage
        if pct is None or pct <= 0 or pct > 100:
            api_error("VALIDATION_ERROR", "sample_percentage must be in (0, 100] for a partial review",
                      {"sample_percentage": pct}, 422)

    # DICOM reviews carry a seed (reproduces the draw / stale re-draw); a non-DICOM
    # review takes every non-DICOM file, so there is nothing to sample or seed.
    seed = None if is_non_dicom else (
        payload.sample_seed if payload.sample_seed is not None else secrets.randbelow(2_000_000_000))
    seed_text = str(seed) if seed is not None else "0"

    if is_non_dicom:
        pop_count_q = """
            select count(*) as c
            from recordset_draft_file rdf
            join file f on f.file_id = rdf.file_id
            where rdf.recordset_draft_id = $1 and coalesce(f.is_dicom_file, false) = false
        """
        empty_msg = "Draft has no non-DICOM files to review"
    else:
        pop_count_q = """
            select count(*) as c from (
                select fs.series_instance_uid
                from recordset_draft_file rdf
                join file_series fs on fs.file_id = rdf.file_id
                where rdf.recordset_draft_id = $1
                group by fs.series_instance_uid
            ) p
        """
        empty_msg = "Draft has no series to review"
    review_insert = """
        insert into qc_review (recordset_draft_id, review_status, review_type, sample_percentage,
                               sample_seed, review_notes, when_created, who_created, when_updated, who_updated)
        values ($1, 'open', $2, $3, $4, $5, now(), $6, now(), $6)
        returning *
    """
    # First review on a draft is usually claimed by its creator; extra reviews go
    # to the pickup pool unclaimed. The caller decides via assign_to_caller.
    assign_insert = """
        insert into qc_review_assignment (qc_review_id, assigned_to, assignment_status, share_percentage,
                                          when_created, who_created, when_updated, who_updated)
        values ($1, $3, $4, 100, now(), $2, now(), $2)
        returning *
    """
    # One qc_unit per sampled DICOM series ...
    series_insert = f"""
        insert into qc_unit (qc_review_id, unit_type, series_instance_uid, qc_status, unit_hash, modality, assignment_id)
        with {QC_DRAW_CTE}
        select $5, 'series', suid, 'pending', series_file_hash, modality, $6
        from drawn
        where ($3 = true or rn <= ceil($4::numeric / 100 * mcount))
    """
    # ... or one qc_unit per non-DICOM file (all of them; hashed for staleness).
    file_insert = """
        insert into qc_unit (qc_review_id, unit_type, recordset_draft_file_id, qc_status, unit_hash, assignment_id)
        select $1, 'file', rdf.recordset_draft_file_id, 'pending', f.digest, $2
        from recordset_draft_file rdf
        join file f on f.file_id = rdf.file_id
        where rdf.recordset_draft_id = $3 and coalesce(f.is_dicom_file, false) = false
    """

    try:
        async with db.transaction() as conn:
            cnt = await conn.fetch(pop_count_q, draft_id)
            if not cnt or cnt[0]["c"] == 0:
                api_error("VALIDATION_ERROR", empty_msg, {"recordset_draft_id": draft_id}, 422)

            rev = await conn.fetch(review_insert, draft_id, review_type, pct, seed,
                                   payload.review_notes, current_user.user_id)
            review = rev[0]
            review_id = review["qc_review_id"]

            assigned_to = current_user.user_id if payload.assign_to_caller else None
            assignment_status = "in_progress" if payload.assign_to_caller else "needs_qc"
            asg = await conn.fetch(assign_insert, review_id, current_user.user_id,
                                   assigned_to, assignment_status)
            assignment = asg[0]

            if is_non_dicom:
                await conn.execute(file_insert, review_id, assignment["assignment_id"], draft_id)
                summary = []
            else:
                await conn.execute(series_insert, draft_id, seed_text, is_full, pct,
                                   review_id, assignment["assignment_id"])
                pop_rows = await conn.fetch(QC_POP_PER_MOD, draft_id)
                samp_rows = await conn.fetch(QC_SAMPLED_PER_MOD, review_id)
                summary = qc_modality_summary(pop_rows, samp_rows)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="creating qc review", context={"recordset_draft_id": draft_id})

    return item_response({
        "review": dict(review),
        "assignment": dict(assignment),
        "summary": summary,
    })


@router.get("/recordsets/drafts/{draft_id}/qc-reviews")
# List QC reviews for a draft (with per-review series counts)
async def list_qc_reviews(
    draft_id: int,
    review_status: Optional[str] = Query(default=None),
    review_type: Optional[str] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    where = ["r.recordset_draft_id = $1"]
    values = [draft_id]
    if review_status:
        values.append(review_status)
        where.append(f"r.review_status = ${len(values)}")
    if review_type:
        values.append(review_type)
        where.append(f"r.review_type = ${len(values)}")
    where_sql = "where " + " and ".join(where)

    list_q = f"""
        select r.*,
            coalesce(c.total, 0) as series_total,
            coalesce(c.pending, 0) as series_pending,
            coalesce(c.approved, 0) as series_approved,
            coalesce(c.rejected, 0) as series_rejected,
            coalesce(c.flagged, 0) as series_flagged,
            coalesce(a.assignment_count, 0) as assignment_count,
            coalesce(a.unclaimed_count, 0) as unclaimed_count,
            coalesce(a.assignee_ids, '{{}}') as assignee_ids
        from qc_review r
        left join (
            select qc_review_id,
                count(*) as total,
                count(*) filter (where qc_status = 'pending') as pending,
                count(*) filter (where qc_status = 'approved') as approved,
                count(*) filter (where qc_status = 'rejected') as rejected,
                count(*) filter (where qc_status = 'flagged') as flagged
            from qc_unit group by qc_review_id
        ) c on c.qc_review_id = r.qc_review_id
        left join (
            select qc_review_id,
                count(*) as assignment_count,
                count(*) filter (where assigned_to is null) as unclaimed_count,
                array_remove(array_agg(distinct assigned_to), null) as assignee_ids
            from qc_review_assignment group by qc_review_id
        ) a on a.qc_review_id = r.qc_review_id
        {where_sql}
        order by r.qc_review_id desc
        {page_clause(page, limit)}
    """
    count_q = f"select count(*) as total from qc_review r {where_sql}"

    try:
        rows = await db.fetch(list_q, values)
        total = (await db.fetch(count_q, values))[0]["total"]
    except Exception as e:
        db_error(e, operation="listing qc reviews", context={"recordset_draft_id": draft_id})

    return paged_response(rows, total, page, limit)


@router.get("/qc/reviews/{review_id}")
# QC review detail: review + assignments (counts) + status/modality breakdown (+ stale breakdown)
async def get_qc_review(review_id: int, db: Database = Depends()):
    # Carries the ownership chain (draft -> recordset -> dataset) so the review
    # page can render a full breadcrumb trail without extra round trips. Mirrors
    # the join the assignments list already does.
    review = await db.fetch_one(
        """
        select r.*,
            d.draft_name,
            rs.recordset_id, rs.recordset_name,
            ds.dataset_id, ds.dataset_name
        from qc_review r
        join recordset_draft d on d.recordset_draft_id = r.recordset_draft_id
        join recordset rs on rs.recordset_id = d.recordset_id
        join dataset ds on ds.dataset_id = rs.dataset_id
        where r.qc_review_id = $1
        """,
        [review_id])
    if not review:
        api_error("NOT_FOUND", "QC review not found", {"qc_review_id": review_id}, 404)

    assignments = await db.fetch(
        """
        select a.*,
            coalesce(c.total, 0) as series_total,
            coalesce(c.pending, 0) as series_pending,
            coalesce(c.approved, 0) as series_approved,
            coalesce(c.rejected, 0) as series_rejected,
            coalesce(c.flagged, 0) as series_flagged
        from qc_review_assignment a
        left join (
            select assignment_id,
                count(*) as total,
                count(*) filter (where qc_status = 'pending') as pending,
                count(*) filter (where qc_status = 'approved') as approved,
                count(*) filter (where qc_status = 'rejected') as rejected,
                count(*) filter (where qc_status = 'flagged') as flagged
            from qc_unit group by assignment_id
        ) c on c.assignment_id = a.assignment_id
        where a.qc_review_id = $1
        order by a.assignment_id
        """,
        [review_id],
    )
    by_status = await db.fetch(
        "select qc_status, count(*) as count from qc_unit where qc_review_id = $1 group by qc_status",
        [review_id],
    )
    by_modality = await db.fetch(
        "select coalesce(modality, '(none)') as modality, qc_status, count(*) as count "
        "from qc_unit where qc_review_id = $1 group by coalesce(modality, '(none)'), qc_status",
        [review_id],
    )

    stale_breakdown = None
    # A DICOM (sampled) review can reconstruct what changed; a non-DICOM review has
    # no draw to replay, so it just carries the stale flag with no breakdown.
    if review["review_status"] == "stale" and review["review_type"] != "non_dicom":
        is_full = review["review_type"] == "full"
        seed_text = str(review["sample_seed"]) if review["sample_seed"] is not None else "0"
        recon_q = f"""
            with {QC_DRAW_CTE},
            t as (
                select suid, series_file_hash from drawn
                where ($3 = true or rn <= ceil($4::numeric / 100 * mcount))
            ),
            cur as (
                select series_instance_uid as suid, unit_hash as series_file_hash
                from qc_unit where qc_review_id = $5
            )
            select
                count(*) filter (where t.suid is not null and cur.suid is not null
                                 and t.series_file_hash <> cur.series_file_hash) as changed,
                count(*) filter (where t.suid is not null and cur.suid is null) as would_add,
                count(*) filter (where t.suid is null and cur.suid is not null) as would_drop
            from t full outer join cur on t.suid = cur.suid
        """
        recon = await db.fetch(
            recon_q,
            [review["recordset_draft_id"], seed_text, is_full,
             review["sample_percentage"], review_id],
        )
        stale_breakdown = dict(recon[0]) if recon else None

    return item_response({
        "review": dict(review),
        "assignments": [dict(a) for a in assignments],
        "series_by_status": [dict(r) for r in by_status],
        "series_by_modality": [dict(r) for r in by_modality],
        "stale_breakdown": stale_breakdown,
    })


@router.put("/qc/reviews/{review_id}")
# Update a QC review (status / notes). Type/percentage/seed are immutable (re-draw = clone).
async def update_qc_review(
    review_id: int,
    payload: QCReviewUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    review = await db.fetch_one("select * from qc_review where qc_review_id = $1", [review_id])
    if not review:
        api_error("NOT_FOUND", "QC review not found", {"qc_review_id": review_id}, 404)

    new_status = payload.review_status
    if new_status is not None:
        if new_status not in VALID_REVIEW_STATUS:
            api_error("VALIDATION_ERROR", "Invalid review_status",
                      {"allowed": list(VALID_REVIEW_STATUS)}, 422)
        if new_status == "complete":
            remaining = await db.fetch_one(
                "select count(*) as n from qc_unit where qc_review_id = $1 and qc_status <> 'approved'",
                [review_id],
            )
            if remaining and remaining["n"] > 0:
                api_error("VALIDATION_ERROR",
                          "Review cannot be completed until every series is approved",
                          {"not_approved": remaining["n"]}, 422)

    try:
        updated = await db.fetch_one(
            """
            update qc_review set
                review_status = coalesce($2, review_status),
                review_notes = coalesce($3, review_notes),
                when_updated = now(),
                who_updated = $4
            where qc_review_id = $1
            returning *
            """,
            [review_id, new_status, payload.review_notes, current_user.user_id],
        )
    except Exception as e:
        db_error(e, operation="updating qc review", context={"qc_review_id": review_id})

    return item_response(updated)


@router.put("/qc/reviews/{review_id}/cancel")
# Soft-cancel a QC review (no hard delete; row + series kept for audit)
async def cancel_qc_review(
    review_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updated = await db.fetch_one(
        "update qc_review set review_status = 'cancelled', when_updated = now(), who_updated = $2 "
        "where qc_review_id = $1 returning *",
        [review_id, current_user.user_id],
    )
    if not updated:
        api_error("NOT_FOUND", "QC review not found", {"qc_review_id": review_id}, 404)
    return item_response(updated)


@router.post("/qc/reviews/{review_id}/clone")
# Clone a review: re-draw against its own draft (same seed) and overlay carried statuses
async def clone_qc_review(
    review_id: int,
    payload: QCReviewClone,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    source = await db.fetch_one("select * from qc_review where qc_review_id = $1", [review_id])
    if not source:
        api_error("NOT_FOUND", "QC review not found", {"qc_review_id": review_id}, 404)

    mode = payload.mode or "carry_forward"
    if mode not in ("carry_forward", "resample"):
        api_error("VALIDATION_ERROR", "mode must be 'carry_forward' or 'resample'", {"mode": mode}, 422)

    is_resample = mode == "resample"
    is_full = source["review_type"] == "full"
    draft_id = source["recordset_draft_id"]
    pct = source["sample_percentage"]
    seed = secrets.randbelow(2_000_000_000) if is_resample else (source["sample_seed"] or 0)
    seed_text = str(seed)

    review_insert = """
        insert into qc_review (recordset_draft_id, review_status, review_type, sample_percentage,
                               sample_seed, review_notes, cloned_from_review_id,
                               when_created, who_created, when_updated, who_updated)
        values ($1, 'open', $2, $3, $4, $5, $6, now(), $7, now(), $7)
        returning *
    """
    assign_insert = """
        insert into qc_review_assignment (qc_review_id, assigned_to, assignment_status, share_percentage,
                                          when_created, who_created, when_updated, who_updated)
        values ($1, null, 'needs_qc', 100, now(), $2, now(), $2)
        returning *
    """
    series_insert = f"""
        insert into qc_unit (qc_review_id, unit_type, series_instance_uid, qc_status, unit_hash, modality, assignment_id)
        with {QC_DRAW_CTE},
        sel as (
            select suid, modality, series_file_hash from drawn
            where ($3 = true or rn <= ceil($4::numeric / 100 * mcount))
        )
        select $5, 'series', sel.suid,
            case when $7 = true then 'pending'
                 when s.series_instance_uid is not null and s.unit_hash = sel.series_file_hash
                     then s.qc_status
                 else 'pending' end,
            sel.series_file_hash, sel.modality, $6
        from sel
        left join qc_unit s on s.qc_review_id = $8 and s.series_instance_uid = sel.suid
    """
    reconcile_q = """
        with newr as (
            select series_instance_uid as suid, unit_hash as series_file_hash from qc_unit where qc_review_id = $1
        ),
        src as (
            select series_instance_uid as suid, unit_hash as series_file_hash from qc_unit where qc_review_id = $2
        )
        select
            count(*) filter (where src.suid is not null and newr.series_file_hash = src.series_file_hash)
                as carried_unchanged,
            count(*) filter (where src.suid is not null and newr.series_file_hash <> src.series_file_hash)
                as changed,
            count(*) filter (where src.suid is null) as added,
            (select count(*) from src where suid not in (select suid from newr)) as dropped
        from newr left join src on newr.suid = src.suid
    """

    try:
        async with db.transaction() as conn:
            rev = await conn.fetch(review_insert, draft_id, source["review_type"], pct, seed,
                                   payload.review_notes, review_id, current_user.user_id)
            review = rev[0]
            new_id = review["qc_review_id"]

            asg = await conn.fetch(assign_insert, new_id, current_user.user_id)
            assignment = asg[0]

            await conn.execute(series_insert, draft_id, seed_text, is_full, pct,
                               new_id, assignment["assignment_id"], is_resample, review_id)

            pop_rows = await conn.fetch(QC_POP_PER_MOD, draft_id)
            samp_rows = await conn.fetch(QC_SAMPLED_PER_MOD, new_id)
            recon = await conn.fetch(reconcile_q, new_id, review_id)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="cloning qc review", context={"qc_review_id": review_id})

    return item_response({
        "review": dict(review),
        "assignment": dict(assignment),
        "summary": qc_modality_summary(pop_rows, samp_rows),
        "reconcile": dict(recon[0]) if recon else None,
    })


@router.post("/qc/reviews/{review_id}/split")
# Rebalance a review across N slices, stratified evenly per modality (contiguous chunks)
async def split_qc_review(
    review_id: int,
    payload: QCSplitRequest,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if (payload.user_ids is None) == (payload.count is None):
        api_error("VALIDATION_ERROR", "Provide exactly one of user_ids or count", {}, 422)

    if payload.user_ids is not None:
        assignees = list(payload.user_ids)
        if len(assignees) < 1:
            api_error("VALIDATION_ERROR", "user_ids must be non-empty", {}, 422)
    else:
        if payload.count < 1:
            api_error("VALIDATION_ERROR", "count must be >= 1", {}, 422)
        assignees = [None] * payload.count

    n = len(assignees)
    share = round(100.0 / n, 4)

    review = await db.fetch_one("select qc_review_id from qc_review where qc_review_id = $1", [review_id])
    if not review:
        api_error("NOT_FOUND", "QC review not found", {"qc_review_id": review_id}, 404)

    assign_insert = """
        insert into qc_review_assignment (qc_review_id, assigned_to, assignment_status, share_percentage,
                                          when_created, who_created, when_updated, who_updated)
        values ($1, $2, 'needs_qc', $3, now(), $4, now(), $4)
        returning assignment_id
    """

    try:
        async with db.transaction() as conn:
            existing = await conn.fetch(
                "select assignment_status from qc_review_assignment where qc_review_id = $1", review_id)
            if not payload.force and any(
                    a["assignment_status"] in ("in_progress", "complete") for a in existing):
                api_error("CONFLICT",
                          "Review has in-progress/complete assignments; pass force=true to rebalance",
                          {"qc_review_id": review_id}, 409)

            units = await conn.fetch(
                "select qc_unit_id, modality from qc_unit "
                "where qc_review_id = $1 order by modality nulls first, qc_unit_id",
                review_id)

            # A slice with no units is meaningless (it can never be worked or
            # completed), so the allocator must never be asked for more slices
            # than there are units.
            if len(units) == 0:
                api_error("VALIDATION_ERROR",
                          "Review has no units to split",
                          {"qc_review_id": review_id}, 422)
            if n > len(units):
                api_error("VALIDATION_ERROR",
                          f"Cannot split {len(units)} unit(s) across {n} slices; "
                          f"at most {len(units)} slices are possible",
                          {"qc_review_id": review_id,
                           "unit_count": len(units),
                           "requested_slices": n}, 422)

            # Group units per modality (file units share the null-modality group),
            # preserving order so each slice gets a contiguous chunk.
            groups = {}
            for r in units:
                groups.setdefault(r["modality"], []).append(r["qc_unit_id"])

            # Even per-modality allocation; round-robin each modality's leftover
            # with a running pointer (not the modality index) so slice totals
            # stay balanced to within 1 across the whole review.
            alloc = [[] for _ in range(n)]
            leftover = 0
            for unit_ids in groups.values():
                c = len(unit_ids)
                counts = [c // n] * n
                rem = c % n
                for k in range(rem):
                    counts[(leftover + k) % n] += 1
                leftover = (leftover + rem) % n
                idx = 0
                for si in range(n):
                    alloc[si].extend(unit_ids[idx:idx + counts[si]])
                    idx += counts[si]

            new_ids = []
            for si in range(n):
                row = await conn.fetch(assign_insert, review_id, assignees[si], share, current_user.user_id)
                aid = row[0]["assignment_id"]
                new_ids.append(aid)
                if alloc[si]:
                    await conn.execute(
                        "update qc_unit set assignment_id = $1 "
                        "where qc_review_id = $2 and qc_unit_id = any($3::int[])",
                        aid, review_id, alloc[si])

            # Drop the old slices (now unreferenced).
            await conn.execute(
                "delete from qc_review_assignment where qc_review_id = $1 and assignment_id <> all($2::int[])",
                review_id, new_ids)

            # Slices are inserted as 'needs_qc', but a split only moves units --
            # it never changes a decision. A slice that inherits already-decided
            # units is complete on arrival, so re-derive each one's status rather
            # than leaving it claiming work that is already done.
            for aid in new_ids:
                await qc_sync_assignment_status(conn, aid)

            result = await conn.fetch(
                """
                select a.*,
                    coalesce(c.total, 0) as series_total
                from qc_review_assignment a
                left join (select assignment_id, count(*) as total from qc_unit group by assignment_id) c
                    on c.assignment_id = a.assignment_id
                where a.qc_review_id = $1
                order by a.assignment_id
                """,
                review_id)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="splitting qc review", context={"qc_review_id": review_id})

    return list_response([dict(r) for r in result])


# ----------------------------------- QC ASSIGNMENTS ----------------------------------

@router.get("/qc/reviews/{review_id}/assignments")
# List a review's assignment slices (with series counts)
async def list_review_assignments(review_id: int, db: Database = Depends()):
    rows = await db.fetch(
        """
        select a.*,
            coalesce(c.total, 0) as series_total,
            coalesce(c.pending, 0) as series_pending,
            coalesce(c.approved, 0) as series_approved,
            coalesce(c.rejected, 0) as series_rejected,
            coalesce(c.flagged, 0) as series_flagged
        from qc_review_assignment a
        left join (
            select assignment_id, count(*) as total,
                count(*) filter (where qc_status = 'pending') as pending,
                count(*) filter (where qc_status = 'approved') as approved,
                count(*) filter (where qc_status = 'rejected') as rejected,
                count(*) filter (where qc_status = 'flagged') as flagged
            from qc_unit group by assignment_id
        ) c on c.assignment_id = a.assignment_id
        where a.qc_review_id = $1
        order by a.assignment_id
        """,
        [review_id])
    return list_response([dict(r) for r in rows])


@router.get("/qc/assignments")
# Queue queries: pickup pool (unassigned + needs_qc) or a user's queue
async def list_qc_assignments(
    status: Optional[str] = Query(default=None),
    assigned_to: Optional[int] = Query(default=None),
    review_id: Optional[int] = Query(default=None),
    recordset_draft_id: Optional[int] = Query(default=None),
    unassigned: Optional[bool] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    where = []
    values = []
    if status:
        values.append(status)
        where.append(f"a.assignment_status = ${len(values)}")
    if assigned_to is not None:
        values.append(assigned_to)
        where.append(f"a.assigned_to = ${len(values)}")
    if review_id is not None:
        values.append(review_id)
        where.append(f"a.qc_review_id = ${len(values)}")
    if recordset_draft_id is not None:
        values.append(recordset_draft_id)
        where.append(f"r.recordset_draft_id = ${len(values)}")
    if unassigned is True:
        where.append("a.assigned_to is null")
    # This is a work-queue endpoint (pickup pool / a user's queue); a cancelled
    # review has no work, so its lingering slices never belong here. The rows
    # stay in the DB for audit -- they're just filtered out of the queue.
    where.append("r.review_status <> 'cancelled'")
    where_sql = "where " + " and ".join(where)

    list_q = f"""
        select a.*,
            coalesce(c.total, 0) as series_total,
            coalesce(c.pending, 0) as series_pending,
            coalesce(c.approved, 0) as series_approved,
            r.review_type, r.review_status, r.recordset_draft_id,
            rs.recordset_id, rs.recordset_name
        from qc_review_assignment a
        join qc_review r on r.qc_review_id = a.qc_review_id
        join recordset_draft d on d.recordset_draft_id = r.recordset_draft_id
        join recordset rs on rs.recordset_id = d.recordset_id
        left join (
            select assignment_id, count(*) as total,
                count(*) filter (where qc_status = 'pending') as pending,
                count(*) filter (where qc_status = 'approved') as approved
            from qc_unit group by assignment_id
        ) c on c.assignment_id = a.assignment_id
        {where_sql}
        order by a.qc_review_id, a.assignment_id
        {page_clause(page, limit)}
    """
    count_q = f"""
        select count(*) as total
        from qc_review_assignment a
        join qc_review r on r.qc_review_id = a.qc_review_id
        {where_sql}
    """

    try:
        rows = await db.fetch(list_q, values)
        total = (await db.fetch(count_q, values))[0]["total"]
    except Exception as e:
        db_error(e, operation="listing qc assignments")
    return paged_response(rows, total, page, limit)


@router.get("/qc/assignments/{assignment_id}")
# Assignment detail + parent review summary + series counts
async def get_qc_assignment(assignment_id: int, db: Database = Depends()):
    assignment = await db.fetch_one(
        "select * from qc_review_assignment where assignment_id = $1", [assignment_id])
    if not assignment:
        api_error("NOT_FOUND", "Assignment not found", {"assignment_id": assignment_id}, 404)

    review = await db.fetch_one(
        "select qc_review_id, recordset_draft_id, review_type, review_status, sample_percentage "
        "from qc_review where qc_review_id = $1", [assignment["qc_review_id"]])
    by_status = await db.fetch(
        "select qc_status, count(*) as count from qc_unit where assignment_id = $1 group by qc_status",
        [assignment_id])
    by_modality = await db.fetch(
        "select coalesce(modality, '(none)') as modality, qc_status, count(*) as count "
        "from qc_unit where assignment_id = $1 group by coalesce(modality, '(none)'), qc_status",
        [assignment_id])

    return item_response({
        "assignment": dict(assignment),
        "review": dict(review) if review else None,
        "series_by_status": [dict(r) for r in by_status],
        "series_by_modality": [dict(r) for r in by_modality],
    })


@router.put("/qc/assignments/{assignment_id}")
# Update an assignment (reassign / set status)
async def update_qc_assignment(
    assignment_id: int,
    payload: QCAssignmentUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updated = await db.fetch_one(
        """
        update qc_review_assignment set
            assigned_to = coalesce($2, assigned_to),
            assignment_status = coalesce(
                $3,
                case when $2 is not null then 'in_progress'
                     else assignment_status end),
            when_updated = now(),
            who_updated = $4
        where assignment_id = $1
        returning *
        """,
        [assignment_id, payload.assigned_to, payload.assignment_status, current_user.user_id])
    if not updated:
        api_error("NOT_FOUND", "Assignment not found", {"assignment_id": assignment_id}, 404)
    return item_response(updated)


@router.post("/qc/assignments/{assignment_id}/claim")
# Claim an unclaimed slice from the pickup pool
async def claim_qc_assignment(
    assignment_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updated = await db.fetch_one(
        """
        update qc_review_assignment set
            assigned_to = $2,
            assignment_status = 'in_progress',
            when_updated = now(),
            who_updated = $2
        where assignment_id = $1 and assigned_to is null
          and (select review_status from qc_review r
               where r.qc_review_id = qc_review_assignment.qc_review_id)
              not in ('cancelled', 'complete')
        returning *
        """,
        [assignment_id, current_user.user_id])
    if not updated:
        # Distinguish a terminal review from a missing / already-claimed slice
        # so the message is actionable.
        info = await db.fetch_one(
            """
            select r.review_status from qc_review_assignment a
            join qc_review r on r.qc_review_id = a.qc_review_id
            where a.assignment_id = $1
            """,
            [assignment_id])
        if not info:
            api_error("NOT_FOUND", "Assignment not found", {"assignment_id": assignment_id}, 404)
        if info["review_status"] in ("cancelled", "complete"):
            api_error("CONFLICT", f"Cannot claim a slice on a {info['review_status']} review",
                      {"assignment_id": assignment_id, "review_status": info["review_status"]}, 409)
        api_error("CONFLICT", "Assignment is not available to claim (already claimed)",
                  {"assignment_id": assignment_id}, 409)
    return item_response(updated)


@router.post("/qc/assignments/{assignment_id}/release")
# Release a slice back to the pickup pool
async def release_qc_assignment(
    assignment_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    updated = await db.fetch_one(
        """
        update qc_review_assignment set
            assigned_to = null,
            assignment_status = 'needs_qc',
            when_updated = now(),
            who_updated = $2
        where assignment_id = $1
        returning *
        """,
        [assignment_id, current_user.user_id])
    if not updated:
        api_error("NOT_FOUND", "Assignment not found", {"assignment_id": assignment_id}, 404)
    return item_response(updated)


@router.post("/qc/assignments/{assignment_id}/complete-for-testing")
# TEST HELPER: approve every series in the slice and complete the slice -- a
# shortcut to stand up QC state for Bundle-stage testing. Not a real reviewer
# action; does NOT touch the parent review's status.
async def complete_assignment_for_testing(
    assignment_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    try:
        async with db.transaction() as conn:
            exists = await conn.fetch(
                "select 1 from qc_unit where assignment_id = $1 limit 1", assignment_id)
            if not exists:
                api_error("NOT_FOUND", "Assignment has no units", {"assignment_id": assignment_id}, 404)
            # Approve every unit -> 0 pending -> qc_sync flips the slice to 'complete'.
            await qc_approve_all_units(conn, assignment_id, current_user.user_id, "complete for testing")
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="completing assignment for testing",
                 context={"assignment_id": assignment_id})

    return item_response({"assignment_id": assignment_id})


@router.post("/qc/assignments/{assignment_id}/approve-units")
# Approve every unit in a slice -- the non-DICOM reviewer action (the modal's
# "Mark Approved"): the reviewer confirms the slice's files after downloading
# them. Writes history per unit and lets qc_sync complete the slice.
async def approve_assignment_units(
    assignment_id: int,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    try:
        async with db.transaction() as conn:
            exists = await conn.fetch(
                "select 1 from qc_unit where assignment_id = $1 limit 1", assignment_id)
            if not exists:
                api_error("NOT_FOUND", "Assignment has no units", {"assignment_id": assignment_id}, 404)
            approved = await qc_approve_all_units(conn, assignment_id, current_user.user_id, "approved")
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="approving assignment units",
                 context={"assignment_id": assignment_id})

    return item_response({"assignment_id": assignment_id, "approved": approved})


# ---------------------------- QC SERIES (viz tool consumes) --------------------------

@router.get("/qc/assignments/{assignment_id}/series")
# List an assignment's series, optionally filtered by status / modality
async def list_assignment_series(
    assignment_id: int,
    qc_status: Optional[str] = Query(default=None),
    modality: Optional[str] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    db: Database = Depends()):

    # DICOM series only -- this is the Mirabelle-facing list; non-DICOM file units
    # are reviewed through a different path.
    where = ["assignment_id = $1", "unit_type = 'series'"]
    values = [assignment_id]
    if qc_status:
        values.append(qc_status)
        where.append(f"qc_status = ${len(values)}")
    if modality:
        values.append(modality)
        where.append(f"modality = ${len(values)}")
    where_sql = "where " + " and ".join(where)

    list_q = f"""
        select qc_review_id, series_instance_uid, qc_status, unit_hash as series_file_hash, modality, assignment_id, notes
        from qc_unit
        {where_sql}
        order by series_instance_uid
        {page_clause(page, limit)}
    """
    count_q = f"select count(*) as total from qc_unit {where_sql}"

    try:
        rows = await db.fetch(list_q, values)
        total = (await db.fetch(count_q, values))[0]["total"]
    except Exception as e:
        db_error(e, operation="listing assignment series", context={"assignment_id": assignment_id})
    return paged_response(rows, total, page, limit)


@router.get("/qc/assignments/{assignment_id}/series/summary")
# Status / modality counts for an assignment (filter chips + progress)
async def assignment_series_summary(assignment_id: int, db: Database = Depends()):
    by_status = await db.fetch(
        "select qc_status, count(*) as count from qc_unit where assignment_id = $1 group by qc_status",
        [assignment_id])
    by_modality = await db.fetch(
        "select coalesce(modality, '(none)') as modality, qc_status, count(*) as count "
        "from qc_unit where assignment_id = $1 group by coalesce(modality, '(none)'), qc_status",
        [assignment_id])
    return item_response({
        "by_status": [dict(r) for r in by_status],
        "by_modality": [dict(r) for r in by_modality],
    })


@router.get("/qc/assignments/{assignment_id}/series/{series_instance_uid}/files")
# Files for a single series in an assignment, ordered by instance number
async def list_assignment_series_files(
    assignment_id: int,
    series_instance_uid: str,
    db: Database = Depends()):

    series = await db.fetch_one(
        "select qc_review_id from qc_unit where assignment_id = $1 and series_instance_uid = $2",
        [assignment_id, series_instance_uid])
    if not series:
        api_error("NOT_FOUND", "Series not found in this assignment",
                  {"assignment_id": assignment_id, "series_instance_uid": series_instance_uid}, 404)

    rows = await db.fetch(
        """
        select
            rdf.file_id,
            coalesce(i.number_of_frames, 1) as num_of_frames,
            fl.file_storage_root_id || '/' || fl.rel_path     as file_path
        from qc_unit qs
        join qc_review qr           on qr.qc_review_id    = qs.qc_review_id
        join recordset_draft_file rdf on rdf.recordset_draft_id = qr.recordset_draft_id
        join file_series fs          on fs.file_id         = rdf.file_id
                                    and fs.series_instance_uid = qs.series_instance_uid
        left join file_location fl      on fl.file_id             = rdf.file_id
        left join file_image fi         on fi.file_id             = rdf.file_id
        left join image i               on i.image_id             = fi.image_id
        left join file_sop_common fsc   on fsc.file_id            = rdf.file_id
        where qs.assignment_id = $1 and qs.series_instance_uid = $2
        order by
            case when fsc.instance_number is null or fsc.instance_number = ''
                 then 0
                 else fsc.instance_number::int
            end
        """,
        [assignment_id, series_instance_uid])

    data = [dict(r) for r in rows]
    return {
        "data": data,
        "meta": {
            "count": len(data),
            "assignment_id": assignment_id,
            "series_instance_uid": series_instance_uid,
        },
    }


@router.put("/qc/assignments/{assignment_id}/series/{series_instance_uid}/status")
# Set one series' QC status (writes history; any authorized user)
async def set_series_status(
    assignment_id: int,
    series_instance_uid: str,
    payload: QCSeriesStatusUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if payload.qc_status not in VALID_QC_STATUS:
        api_error("VALIDATION_ERROR", "Invalid qc_status", {"allowed": list(VALID_QC_STATUS)}, 422)

    try:
        async with db.transaction() as conn:
            row = await conn.fetch(
                "select qc_unit_id, qc_status from qc_unit "
                "where assignment_id = $1 and series_instance_uid = $2",
                assignment_id, series_instance_uid)
            if not row:
                api_error("NOT_FOUND", "Series not found in this assignment",
                          {"assignment_id": assignment_id, "series_instance_uid": series_instance_uid}, 404)
            unit_id = row[0]["qc_unit_id"]
            previous = row[0]["qc_status"]

            updated = await conn.fetch(
                "update qc_unit set qc_status = $1, notes = coalesce($2, notes) "
                "where qc_unit_id = $3 returning *",
                payload.qc_status, payload.notes, unit_id)

            await conn.execute(
                "insert into qc_unit_history (qc_unit_id, previous_status, "
                "new_status, who_updated, notes) values ($1, $2, $3, $4, $5)",
                unit_id, previous, payload.qc_status, current_user.user_id, payload.notes)

            await qc_sync_assignment_status(conn, assignment_id)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="setting series status", context={"assignment_id": assignment_id})

    return item_response(dict(updated[0]))


@router.put("/qc/assignments/{assignment_id}/series/status")
# Batch-set status for many series in one transaction (history per series)
async def set_series_status_batch(
    assignment_id: int,
    payload: QCSeriesBatchStatus,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if payload.qc_status not in VALID_QC_STATUS:
        api_error("VALIDATION_ERROR", "Invalid qc_status", {"allowed": list(VALID_QC_STATUS)}, 422)
    if not payload.series_instance_uids:
        api_error("VALIDATION_ERROR", "series_instance_uids must be non-empty", {}, 422)

    try:
        async with db.transaction() as conn:
            rows = await conn.fetch(
                "select qc_unit_id, qc_status from qc_unit "
                "where assignment_id = $1 and series_instance_uid = any($2::text[])",
                assignment_id, payload.series_instance_uids)
            if not rows:
                api_error("NOT_FOUND", "No matching series in this assignment",
                          {"assignment_id": assignment_id}, 404)

            await conn.execute(
                "update qc_unit set qc_status = $1, notes = coalesce($2, notes) "
                "where assignment_id = $3 and series_instance_uid = any($4::text[])",
                payload.qc_status, payload.notes, assignment_id, payload.series_instance_uids)

            for r in rows:
                await conn.execute(
                    "insert into qc_unit_history (qc_unit_id, previous_status, "
                    "new_status, who_updated, notes) values ($1, $2, $3, $4, $5)",
                    r["qc_unit_id"], r["qc_status"], payload.qc_status,
                    current_user.user_id, payload.notes)

            await qc_sync_assignment_status(conn, assignment_id)
    except HTTPException:
        raise
    except Exception as e:
        db_error(e, operation="batch setting series status", context={"assignment_id": assignment_id})

    return item_response({"updated": len(rows)})


@router.get("/qc/assignments/{assignment_id}/series/{series_instance_uid}/history")
# Read the status-change history for one series
async def get_series_history(assignment_id: int, series_instance_uid: str, db: Database = Depends()):
    row = await db.fetch_one(
        "select qc_unit_id from qc_unit where assignment_id = $1 and series_instance_uid = $2",
        [assignment_id, series_instance_uid])
    if not row:
        api_error("NOT_FOUND", "Series not found in this assignment",
                  {"assignment_id": assignment_id, "series_instance_uid": series_instance_uid}, 404)
    history = await db.fetch(
        "select * from qc_unit_history where qc_unit_id = $1 order by when_updated desc",
        [row["qc_unit_id"]])
    return list_response([dict(r) for r in history])


# ----------------------------------- USER FLAGS --------------------------------------

@router.post("/flags")
# Create a per-user action-item flag (launch scope: object_type='qc_review')
async def create_user_flag(
    payload: UserFlagCreate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    if payload.object_type != "qc_review":
        api_error("VALIDATION_ERROR", "object_type must be 'qc_review' (launch scope)",
                  {"object_type": payload.object_type}, 422)

    try:
        created = await db.fetch_one(
            """
            insert into user_flag (object_type, object_id, series_instance_uid, flagged_for,
                                   flagged_by, note, flag_status, when_created)
            values ($1, $2, $3, $4, $5, $6, 'open', now())
            returning *
            """,
            [payload.object_type, payload.object_id, payload.series_instance_uid,
             payload.flagged_for, current_user.user_id, payload.note])
    except Exception as e:
        db_error(e, operation="creating user flag")
    return item_response(created)


@router.get("/flags")
# List flags (dashboard action items via flagged_for=me&status=open, or flags on an object)
async def list_user_flags(
    flagged_for: Optional[str] = Query(default=None),
    flagged_by: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    object_type: Optional[str] = Query(default=None),
    object_id: Optional[int] = Query(default=None),
    page: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    current_user: User = logged_in_user,
    db: Database = Depends()):

    where = []
    values = []
    if flagged_for is not None:
        target = current_user.user_id if flagged_for == "me" else int(flagged_for)
        values.append(target)
        where.append(f"flagged_for = ${len(values)}")
    if flagged_by is not None:
        values.append(flagged_by)
        where.append(f"flagged_by = ${len(values)}")
    if status:
        values.append(status)
        where.append(f"flag_status = ${len(values)}")
    if object_type:
        values.append(object_type)
        where.append(f"object_type = ${len(values)}")
    if object_id is not None:
        values.append(object_id)
        where.append(f"object_id = ${len(values)}")
    where_sql = ("where " + " and ".join(where)) if where else ""

    list_q = f"select * from user_flag {where_sql} order by when_created desc {page_clause(page, limit)}"
    count_q = f"select count(*) as total from user_flag {where_sql}"

    try:
        rows = await db.fetch(list_q, values)
        total = (await db.fetch(count_q, values))[0]["total"]
    except Exception as e:
        db_error(e, operation="listing user flags")
    return paged_response(rows, total, page, limit)


@router.put("/flags/{user_flag_id}")
# Resolve / reopen / edit a flag (any authorized user)
async def update_user_flag(
    user_flag_id: int,
    payload: UserFlagUpdate,
    current_user: User = logged_in_user,
    db: Database = Depends()):

    flag = await db.fetch_one("select * from user_flag where user_flag_id = $1", [user_flag_id])
    if not flag:
        api_error("NOT_FOUND", "Flag not found", {"user_flag_id": user_flag_id}, 404)

    if payload.flag_status is not None and payload.flag_status not in ("open", "resolved"):
        api_error("VALIDATION_ERROR", "flag_status must be 'open' or 'resolved'", {}, 422)

    resolving = payload.flag_status == "resolved"
    reopening = payload.flag_status == "open"

    try:
        updated = await db.fetch_one(
            """
            update user_flag set
                flag_status = coalesce($2, flag_status),
                note = coalesce($3, note),
                flagged_for = coalesce($4, flagged_for),
                when_resolved = case when $5 then now() when $6 then null else when_resolved end,
                who_resolved  = case when $5 then $7   when $6 then null else who_resolved  end
            where user_flag_id = $1
            returning *
            """,
            [user_flag_id, payload.flag_status, payload.note, payload.flagged_for,
             resolving, reopening, current_user.user_id])
    except Exception as e:
        db_error(e, operation="updating user flag", context={"user_flag_id": user_flag_id})

    return item_response(updated)
