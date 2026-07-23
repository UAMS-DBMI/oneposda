import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from .auth import logged_in_user
from .distribution import api_error, db_error
from ..util import Database
from ..util.wp import (
    wp_get, wp_post, wp_patch, wp_delete, wp_get_paged, wp_get_media_paged,
    wp_url, wp_edit_url, _params,
    WP_TYPE_MAP,
    format_media, format_citation, format_collection, format_analysis_result,
    format_download, format_version, format_version_download,
    format_cancer_type, format_location, format_species, format_data_type,
    format_supporting_data, format_file_type, format_license,
    format_requirement, format_program,
)

router = APIRouter(
    tags=["Manager"],
    dependencies=[logged_in_user]
)

# ----------------------------
# Endpoints
# ----------------------------


@router.get("/media")
async def get_media(search: str = None, mime_type: str = None):
    try:
        p = {}
        if search:    p["search"]    = search
        if mime_type: p["mime_type"] = mime_type
        return [format_media(i) for i in await wp_get_media_paged(params=p)]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/media/{post_id}")
async def get_media_item(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Media')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Media not found")
        return format_media(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/citations")
async def get_citations(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_citation(i) for i in await wp_get_paged(wp_url("Citation"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/citations/{post_id}")
async def get_citation(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Citation')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Citation not found")
        return format_citation(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/collections")
async def get_wp_collections(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_collection(i) for i in await wp_get_paged(wp_url("Collection"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/collections/{post_id}")
async def get_wp_collection(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Collection')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Collection not found")
        return format_collection(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/analysis-results")
async def get_analysis_results(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_analysis_result(i) for i in await wp_get_paged(wp_url("Analysis Result"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/analysis-results/{post_id}")
async def get_analysis_result(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Analysis Result')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Analysis Result not found")
        return format_analysis_result(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/downloads")
async def get_wp_downloads(
    slug: str = None,
    search: str = None,
    status: str = "publish,draft",
    ids: str = None,
    download_type: str = None,
    download_access: str = None,
):
    try:
        results = [format_download(i) for i in await wp_get_paged(wp_url("Download"), _params(slug, search, status, ids))]
        if download_type:
            results = [r for r in results if r.get("download_type") == download_type]
        if download_access:
            results = [r for r in results if r.get("download_access") == download_access]
        return results
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/downloads/{post_id}")
async def get_wp_download(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Download')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Download not found")
        return format_download(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/versions")
async def get_versions(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_version(i) for i in await wp_get_paged(wp_url("Version"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/versions/{post_id}")
async def get_version(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Version')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Version not found")
        return format_version(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/version-downloads")
async def get_version_downloads(
    slug: str = None,
    search: str = None,
    status: str = "publish,draft",
    ids: str = None,
    download_type: str = None,
    download_access: str = None,
):
    try:
        results = [format_version_download(i) for i in await wp_get_paged(wp_url("Version Download"), _params(slug, search, status, ids))]
        if download_type:
            results = [r for r in results if r.get("download_type") == download_type]
        if download_access:
            results = [r for r in results if r.get("download_access") == download_access]
        return results
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/version-downloads/{post_id}")
async def get_version_download(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Version Download')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Version Download not found")
        return format_version_download(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/cancer-types")
async def get_cancer_types(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_cancer_type(i) for i in await wp_get_paged(wp_url("Cancer Type"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/cancer-types/{post_id}")
async def get_cancer_type(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Cancer Type')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Cancer Type not found")
        return format_cancer_type(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/locations")
async def get_locations(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_location(i) for i in await wp_get_paged(wp_url("Location"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/locations/{post_id}")
async def get_location(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Location')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Location not found")
        return format_location(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/species")
async def get_species(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_species(i) for i in await wp_get_paged(wp_url("Species"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/species/{post_id}")
async def get_species_item(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Species')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Species not found")
        return format_species(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/data-types")
async def get_data_types(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_data_type(i) for i in await wp_get_paged(wp_url("Data Type"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/data-types/{post_id}")
async def get_data_type(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Data Type')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Data Type not found")
        return format_data_type(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/supporting-data")
async def get_supporting_data(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_supporting_data(i) for i in await wp_get_paged(wp_url("Supporting Data"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/supporting-data/{post_id}")
async def get_supporting_data_item(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Supporting Data')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Supporting Data not found")
        return format_supporting_data(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/file-types")
async def get_file_types(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_file_type(i) for i in await wp_get_paged(wp_url("File Type"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/file-types/{post_id}")
async def get_file_type(post_id: int):
    try:
        item = await wp_get(f"{wp_url('File Type')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="File Type not found")
        return format_file_type(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/licenses")
async def get_licenses(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_license(i) for i in await wp_get_paged(wp_url("License"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/licenses/{post_id}")
async def get_license(post_id: int):
    try:
        item = await wp_get(f"{wp_url('License')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="License not found")
        return format_license(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/requirements")
async def get_requirements(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_requirement(i) for i in await wp_get_paged(wp_url("Requirement"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/requirements/{post_id}")
async def get_requirement(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Requirement')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Requirement not found")
        return format_requirement(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/programs")
async def get_programs(slug: str = None, search: str = None, status: str = "publish,draft", ids: str = None):
    try:
        return [format_program(i) for i in await wp_get_paged(wp_url("Program"), _params(slug, search, status, ids))]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@router.get("/programs/{post_id}")
async def get_program(post_id: int):
    try:
        item = await wp_get(f"{wp_url('Program')}/{post_id}")
        if item is None:
            raise HTTPException(status_code=404, detail="Program not found")
        return format_program(item)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ----------------------------
# wp_object_map models
# ----------------------------

class WpObjectMapInsert(BaseModel):
    posda_object_type: str
    posda_object_id: int
    wp_object_type: str
    wp_object_id: int
    wp_edit_url: Optional[str] = None
    wp_view_url: Optional[str] = None
    parent_wp_object_id: Optional[int] = None

class WpObjectMapUpdate(BaseModel):
    wp_object_type: Optional[str] = None
    wp_object_id: Optional[int] = None
    wp_edit_url: Optional[str] = None
    wp_view_url: Optional[str] = None
    parent_wp_object_id: Optional[int] = None


# ----------------------------
# Attach a recordset's Download onto its dataset's WP page
# ----------------------------

# collection_downloads / result_downloads are plain int arrays of Download
# CPT post IDs -- confirmed against a live WP response, not embedded objects.
DATASET_DOWNLOADS_FIELD = {
    "collection": "collection_downloads",
    "analysis_result": "result_downloads",
}

async def _attach_download_to_dataset(db: Database, recordset_id: int, download_wp_object_id: int) -> Optional[str]:
    """Adds a recordset's linked Download post ID to its dataset's WP page
    (collection_downloads / result_downloads). Doesn't remove stale IDs left
    behind when a recordset is unlinked or relinked to a different download --
    that reconciliation isn't handled yet. Returns an error message on
    failure, None on success or when there's nothing to attach to."""
    rs_rows = await db.fetch("SELECT dataset_id FROM recordset WHERE recordset_id = $1", [recordset_id])
    if not rs_rows:
        return None
    dataset_id = rs_rows[0]["dataset_id"]

    map_rows = await db.fetch(
        "SELECT wp_object_type, wp_object_id FROM wp_object_map "
        "WHERE posda_object_type = 'dataset' AND posda_object_id = $1",
        [dataset_id],
    )
    if not map_rows:
        return None  # dataset has no WP page yet -- nothing to attach to

    wp_object_type = map_rows[0]["wp_object_type"]
    wp_object_id = map_rows[0]["wp_object_id"]
    field_name = DATASET_DOWNLOADS_FIELD.get(wp_object_type)
    entry = WP_TYPE_MAP.get(wp_object_type)
    if not field_name or not entry:
        return None
    endpoint_key, _formatter = entry

    try:
        item = await wp_get(f"{wp_url(endpoint_key)}/{wp_object_id}")
        if item is None:
            return f"The dataset's WordPress {wp_object_type} (id={wp_object_id}) no longer exists."
        current = item.get(field_name) or []
        if download_wp_object_id in current:
            return None
        await wp_patch(f"{wp_url(endpoint_key)}/{wp_object_id}", {field_name: [*current, download_wp_object_id]})
    except httpx.HTTPStatusError as e:
        return f"Linked, but could not update the dataset's {field_name}: {e.response.text}"
    except Exception as e:
        return f"Linked, but could not update the dataset's {field_name}: {type(e).__name__}: {e}"
    return None


# ----------------------------
# wp_object_map CRUD
# ----------------------------

@router.get("/wp-object-map")
async def list_wp_object_map(
    posda_object_type: Optional[str] = Query(default=None),
    posda_object_id: Optional[int] = Query(default=None),
    wp_object_type: Optional[str] = Query(default=None),
    db: Database = Depends(),
):
    where, vals, idx = [], [], 1
    if posda_object_type:
        where.append(f"posda_object_type = ${idx}"); vals.append(posda_object_type); idx += 1
    if posda_object_id is not None:
        where.append(f"posda_object_id = ${idx}"); vals.append(posda_object_id); idx += 1
    if wp_object_type:
        where.append(f"wp_object_type = ${idx}"); vals.append(wp_object_type); idx += 1
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = await db.fetch(f"SELECT * FROM wp_object_map {clause} ORDER BY map_id", vals)
    return {"data": [dict(r) for r in rows]}


@router.get("/wp-object-map/{map_id}")
async def get_wp_object_map(map_id: int, db: Database = Depends()):
    rows = await db.fetch("SELECT * FROM wp_object_map WHERE map_id = $1", [map_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"data": dict(rows[0])}


@router.post("/wp-object-map")
async def create_wp_object_map(payload: WpObjectMapInsert, db: Database = Depends()):
    try:
        rows = await db.fetch(
            """
            INSERT INTO wp_object_map
                (posda_object_type, posda_object_id, wp_object_type, wp_object_id,
                 wp_edit_url, wp_view_url, parent_wp_object_id, when_synced)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            RETURNING *
            """,
            [payload.posda_object_type, payload.posda_object_id,
             payload.wp_object_type, payload.wp_object_id,
             payload.wp_edit_url, payload.wp_view_url, payload.parent_wp_object_id],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    result = {"data": dict(rows[0])}
    if payload.posda_object_type == "recordset" and payload.wp_object_type == "download":
        warning = await _attach_download_to_dataset(db, payload.posda_object_id, payload.wp_object_id)
        if warning:
            result["warning"] = warning
    return result


@router.put("/wp-object-map/{map_id}")
async def update_wp_object_map(map_id: int, payload: WpObjectMapUpdate, db: Database = Depends()):
    rows = await db.fetch("SELECT * FROM wp_object_map WHERE map_id = $1", [map_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Mapping not found")
    current = dict(rows[0])
    updated = await db.fetch(
        """
        UPDATE wp_object_map SET
            wp_object_type      = $2,
            wp_object_id        = $3,
            wp_edit_url         = $4,
            wp_view_url         = $5,
            parent_wp_object_id = $6,
            when_synced         = now()
        WHERE map_id = $1
        RETURNING *
        """,
        [map_id,
         payload.wp_object_type      if payload.wp_object_type      is not None else current["wp_object_type"],
         payload.wp_object_id        if payload.wp_object_id        is not None else current["wp_object_id"],
         payload.wp_edit_url         if payload.wp_edit_url         is not None else current["wp_edit_url"],
         payload.wp_view_url         if payload.wp_view_url         is not None else current["wp_view_url"],
         payload.parent_wp_object_id if payload.parent_wp_object_id is not None else current["parent_wp_object_id"]],
    )
    new_row = dict(updated[0])
    result = {"data": new_row}
    if new_row["posda_object_type"] == "recordset" and new_row["wp_object_type"] == "download":
        warning = await _attach_download_to_dataset(db, new_row["posda_object_id"], new_row["wp_object_id"])
        if warning:
            result["warning"] = warning
    return result


@router.delete("/wp-object-map/{map_id}")
async def delete_wp_object_map(map_id: int, db: Database = Depends()):
    rows = await db.fetch(
        "DELETE FROM wp_object_map WHERE map_id = $1 RETURNING map_id", [map_id]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"data": {"deleted": True, "map_id": map_id}}


# ----------------------------
# Create a new WP object (draft) and link it
# ----------------------------

class WpObjectCreate(BaseModel):
    posda_object_type: str
    posda_object_id: int
    wp_object_type: str
    title: str
    slug: Optional[str] = None
    parent_wp_object_id: Optional[int] = None

class WpObjectStatusUpdate(BaseModel):
    status: str  # "draft" | "publish"

def _slugify(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

@router.post("/wp-objects")
async def create_wp_object(payload: WpObjectCreate, db: Database = Depends()):
    entry = WP_TYPE_MAP.get(payload.wp_object_type)
    if not entry:
        api_error("VALIDATION_ERROR", f"Unsupported wp_object_type: {payload.wp_object_type}", {}, 400)
    endpoint_key, formatter = entry
    slug = payload.slug or _slugify(payload.title)

    try:
        item = await wp_post(wp_url(endpoint_key), {
            "title": payload.title,
            "slug": slug,
            "status": "draft",
        })
    except httpx.HTTPStatusError as e:
        api_error("WP_ERROR", f"WordPress rejected the request: {e.response.text}", {}, e.response.status_code)
    except Exception as e:
        api_error("WP_ERROR", f"Could not reach WordPress: {e}", {}, 500)

    try:
        formatted = formatter(item)
    except Exception as e:
        api_error(
            "INTERNAL_ERROR",
            f"WP {endpoint_key} created (id={item.get('id')}) but its response could not be parsed: {type(e).__name__}: {e}",
            {}, 500,
        )

    try:
        map_rows = await db.fetch(
            """
            INSERT INTO wp_object_map
                (posda_object_type, posda_object_id, wp_object_type, wp_object_id,
                 wp_edit_url, wp_view_url, parent_wp_object_id, when_synced)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT ON CONSTRAINT unq_wp_object_map_posda_object DO UPDATE SET
                wp_object_type      = excluded.wp_object_type,
                wp_object_id        = excluded.wp_object_id,
                wp_edit_url         = excluded.wp_edit_url,
                wp_view_url         = excluded.wp_view_url,
                parent_wp_object_id = excluded.parent_wp_object_id,
                when_synced         = excluded.when_synced
            RETURNING *
            """,
            [payload.posda_object_type, payload.posda_object_id,
             payload.wp_object_type, formatted["id"],
             formatted["edit_url"], formatted["view_url"], payload.parent_wp_object_id],
        )
    except Exception as e:
        db_error(e, operation="linking new WordPress object", context={
            "posda_object_type": payload.posda_object_type,
            "posda_object_id": payload.posda_object_id,
        })

    result = {"data": {"map": dict(map_rows[0]), "object": formatted}}
    if payload.posda_object_type == "recordset" and payload.wp_object_type == "download":
        warning = await _attach_download_to_dataset(db, payload.posda_object_id, formatted["id"])
        if warning:
            result["warning"] = warning
    return result


@router.put("/wp-objects/{map_id}/status")
async def update_wp_object_status(map_id: int, payload: WpObjectStatusUpdate, db: Database = Depends()):
    rows = await db.fetch(
        "SELECT wp_object_type, wp_object_id FROM wp_object_map WHERE map_id = $1", [map_id]
    )
    if not rows:
        api_error("NOT_FOUND", "Mapping not found", {"map_id": map_id}, 404)

    entry = WP_TYPE_MAP.get(rows[0]["wp_object_type"])
    if not entry:
        api_error("VALIDATION_ERROR", f"Unsupported wp_object_type: {rows[0]['wp_object_type']}", {}, 400)
    endpoint_key, formatter = entry

    try:
        item = await wp_patch(f"{wp_url(endpoint_key)}/{rows[0]['wp_object_id']}", {"status": payload.status})
    except httpx.HTTPStatusError as e:
        api_error("WP_ERROR", f"WordPress rejected the request: {e.response.text}", {}, e.response.status_code)
    except Exception as e:
        api_error("WP_ERROR", f"Could not reach WordPress: {e}", {}, 500)

    await db.execute("UPDATE wp_object_map SET when_synced = now() WHERE map_id = $1", [map_id])
    return {"data": formatter(item)}


# ----------------------------
# Fetch live WP metadata via map
# ----------------------------

async def _fetch_wp_object(wp_object_type: str, wp_object_id: int) -> dict:
    entry = WP_TYPE_MAP.get(wp_object_type)
    if not entry:
        raise HTTPException(status_code=400, detail=f"Unsupported wp_object_type: {wp_object_type}")
    endpoint_key, formatter = entry
    try:
        item = await wp_get(f"{wp_url(endpoint_key)}/{wp_object_id}")
        if item is None:
            raise HTTPException(status_code=404, detail=f"WP {wp_object_type} {wp_object_id} not found")
        return formatter(item)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/wp-object-map/{map_id}/wp-object")
async def get_wp_object_for_map(map_id: int, db: Database = Depends()):
    rows = await db.fetch("SELECT wp_object_type, wp_object_id FROM wp_object_map WHERE map_id = $1", [map_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"data": await _fetch_wp_object(rows[0]["wp_object_type"], rows[0]["wp_object_id"])}


@router.get("/posda/{posda_object_type}/{posda_object_id}/wp-map")
async def get_wp_map_for_posda_object(posda_object_type: str, posda_object_id: int, db: Database = Depends()):
    rows = await db.fetch(
        "SELECT * FROM wp_object_map WHERE posda_object_type = $1 AND posda_object_id = $2",
        [posda_object_type, posda_object_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No WP mapping for {posda_object_type} {posda_object_id}")
    return {"data": dict(rows[0])}


@router.get("/posda/{posda_object_type}/{posda_object_id}/wp-object")
async def get_wp_object_for_posda_object(posda_object_type: str, posda_object_id: int, db: Database = Depends()):
    rows = await db.fetch(
        "SELECT wp_object_type, wp_object_id FROM wp_object_map WHERE posda_object_type = $1 AND posda_object_id = $2",
        [posda_object_type, posda_object_id],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No WP mapping for {posda_object_type} {posda_object_id}")
    return {"data": await _fetch_wp_object(rows[0]["wp_object_type"], rows[0]["wp_object_id"])}
