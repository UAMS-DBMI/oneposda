"""Builds the Croissant JSON-LD document for a dataset release.

Ported from generate_tcia_croissant.py in kirbyju/tcia-croissant-odrl (the
"download summary" format the TCIA Data Retriever reads). Only the
document-building logic is kept; the script's SQLite snapshot, DataCite
lookup, ZIP/index output and provenance block are dropped.

Pure functions, no I/O. The caller reads WordPress and the release and passes:
  - the collection / analysis-result page, as format_collection /
    format_analysis_result return it;
  - its download pages, as format_download returns them, each with the media
    URLs resolved into `download_file_url` and `download_metadata_url`;
  - for an analysis result, the source collection's download pages, likewise;
  - the release's number and dates.

The TCIA Data Retriever decides what to do with each download from the text of
its requirements: "Data Retriever" -> expand the linked manifest, "Aspera" ->
skip, anything else with a URL -> download directly.
"""

import html
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any

TCIA_ORG_URL = "https://www.cancerimagingarchive.net/"
TCIA_CATALOG_ID = "https://www.cancerimagingarchive.net/#catalog"
TCIA_DATA_USAGE_POLICY_URL = (
    "https://www.cancerimagingarchive.net/data-usage-policies-and-restrictions/"
)
TCIA_CONTROLLED_ACCESS_POLICY_URL = (
    "https://www.cancerimagingarchive.net/nih-controlled-data-access-policy/"
)
CROISSANT_CONFORMS_TO = "http://mlcommons.org/croissant/1.1"

PAGE_TYPES = {"collection": "Collection", "analysis_result": "Analysis Result"}


@dataclass(frozen=True)
class ReleaseInfo:
    """The dataset release fields the document needs."""

    release_number: int
    release_date: date | None
    first_release_date: date | None


# ----------------------------
# Text helpers
# ----------------------------


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def clean_text(value: Any) -> str:
    """Flattens a WordPress value to plain text; False and [] mean empty."""
    if value is None or value is False:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(clean_text(item) for item in value if clean_text(item))
    if isinstance(value, dict):
        return clean_text(
            value.get("text") or value.get("label") or value.get("url") or ""
        )
    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        text = parser.text()
    return re.sub(r"\s+", " ", text).strip()


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)
    return output


def as_list(value: Any) -> list[str]:
    if value in (None, False, ""):
        return []
    if isinstance(value, (list, tuple)):
        return dedupe([clean_text(item) for item in value])
    return dedupe([clean_text(value)])


def lower_text(*values: Any) -> str:
    return " ".join(clean_text(value) for value in values).casefold()


def doi_url(doi: str) -> str:
    cleaned = doi.strip()
    if not cleaned:
        return ""
    if cleaned.lower().startswith("https://doi.org/"):
        return cleaned
    return f"https://doi.org/{cleaned}"


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug or fallback


def int_value(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def property_value(name: str, value: Any) -> dict[str, Any] | None:
    if value in (None, "", [], {}):
        return None
    return {"@type": "PropertyValue", "name": name, "value": value}


def add_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        target[key] = value


def present(*entries: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry]


# ----------------------------
# Licenses and access
# ----------------------------


def license_url_from_label(label: str) -> str:
    text = label.casefold()
    if "cc by-nc-sa" in text or "cc-by-nc-sa" in text:
        return "https://creativecommons.org/licenses/by-nc-sa/4.0/"
    if "cc by-nc" in text or "cc-by-nc" in text or "noncommercial" in text:
        return "https://creativecommons.org/licenses/by-nc/4.0/"
    if "cc by 4.0" in text or "cc-by-4.0" in text:
        return "https://creativecommons.org/licenses/by/4.0/"
    if "cc by 3.0" in text or "cc-by-3.0" in text:
        return "https://creativecommons.org/licenses/by/3.0/"
    if "nih controlled" in text or "controlled data access" in text:
        return TCIA_CONTROLLED_ACCESS_POLICY_URL
    return ""


def access_level_for_download(download_access: str, license_label: str) -> str:
    """WordPress's download_access (Public | Limited) is authoritative for
    controlled access; the license text separates open from noncommercial."""
    if download_access.casefold() == "limited":
        return "controlled"
    text = license_label.casefold()
    if any(term in text for term in ["nih controlled", "controlled data access"]):
        return "controlled"
    if any(term in text for term in ["noncommercial", "by-nc", "by nc"]):
        return "open_noncommercial"
    if any(term in text for term in ["creative commons", "cc by", "cc-by"]):
        return "open"
    return "review_needed"


def conditions_of_access(access_level: str) -> str:
    if access_level == "controlled":
        return (
            "Controlled-access TCIA data. Users must obtain authorization and "
            "follow the TCIA NIH Controlled Data Access Policy before accessing "
            "this row."
        )
    if access_level == "mixed":
        return (
            "Mixed open and controlled access. Review each TCIA download row for "
            "its license, access mechanism, and controlled-access requirements."
        )
    if access_level == "open_noncommercial":
        return (
            "Open-access TCIA data with a noncommercial-use license condition. "
            "Users must follow the listed license and TCIA Data Usage Policies "
            "and Restrictions."
        )
    if access_level == "open":
        return (
            "Open-access TCIA data. Users must follow the listed license and TCIA "
            "Data Usage Policies and Restrictions."
        )
    if access_level == "metadata only":
        return (
            "Metadata-only TCIA download row; no linked download artifact is "
            "available."
        )
    return (
        "Review the TCIA landing page and download-row metadata for current "
        "access conditions."
    )


def _controlled_access_offer() -> dict[str, Any]:
    return {
        "@type": ["CreativeWork", "odrl:Offer"],
        "@id": TCIA_CONTROLLED_ACCESS_POLICY_URL,
        "name": "TCIA NIH Controlled Data Access Policy",
        "url": TCIA_CONTROLLED_ACCESS_POLICY_URL,
        "description": (
            "Access requires authorization under the TCIA NIH Controlled Data "
            "Access Policy."
        ),
        "odrl:permission": {
            "@type": "odrl:Permission",
            "odrl:action": {"@id": "odrl:use", "name": "Use"},
            "odrl:duty": {
                "@type": "odrl:Duty",
                "odrl:action": {
                    "@id": "odrl:obtainConsent",
                    "name": "Obtain required access approval",
                },
            },
        },
    }


def _noncommercial_offer(license_label: str) -> dict[str, Any]:
    return {
        "@type": ["CreativeWork", "odrl:Offer"],
        "name": "Noncommercial use condition",
        "description": (
            f"{license_label or 'This license'} includes a noncommercial-use "
            "condition."
        ),
        "odrl:permission": {
            "@type": "odrl:Permission",
            "odrl:action": {"@id": "odrl:use", "name": "Use"},
            "odrl:constraint": {
                "@type": "odrl:Constraint",
                "name": "Non-commercial use only",
                "odrl:operator": {"@id": "odrl:eq"},
                "odrl:rightOperand": "noncommercial",
            },
        },
    }


def policy_usage_info(
    access_level: str, license_label: str = "", license_url: str = ""
) -> list[dict[str, Any]]:
    usage: list[dict[str, Any]] = [
        {
            "@type": "CreativeWork",
            "@id": TCIA_DATA_USAGE_POLICY_URL,
            "name": "TCIA Data Usage Policies and Restrictions",
            "url": TCIA_DATA_USAGE_POLICY_URL,
        }
    ]
    if access_level == "controlled":
        usage.append(_controlled_access_offer())
    elif access_level == "open_noncommercial":
        usage.append(_noncommercial_offer(license_label))
    if license_url:
        usage.append(
            {
                "@type": "CreativeWork",
                "@id": license_url,
                "name": license_label or license_url,
                "url": license_url,
            }
        )
    return usage


# ----------------------------
# Download pages
# ----------------------------


def normalize_download(download: dict[str, Any]) -> dict[str, Any]:
    """Maps a formatted WordPress download page to the builder's fields. The
    payload link is the attached file's media URL, else download_url."""
    license_label = clean_text(download.get("data_license"))
    url = clean_text(download.get("download_file_url")) or clean_text(
        download.get("download_url")
    )
    return {
        "id": clean_text(download.get("id")),
        "title": clean_text(download.get("download_title"))
        or clean_text(download.get("title")),
        "url": url,
        "search_url": clean_text(download.get("search_url")),
        "metadata_url": clean_text(download.get("download_metadata_url")),
        "description": clean_text(download.get("description")),
        "license_label": license_label,
        "license_url": license_url_from_label(license_label),
        "requirements": clean_text(download.get("download_requirements")),
        "download_size": clean_text(download.get("download_size")),
        "download_size_unit": clean_text(download.get("download_size_unit")),
        "download_types": as_list(download.get("download_type")),
        "data_types": as_list(download.get("data_type")),
        "file_types": as_list(download.get("file_type")),
        "subjects": clean_text(download.get("subjects")),
        "studies": clean_text(download.get("study_count")),
        "series": clean_text(download.get("series_count")),
        "images": clean_text(download.get("image_count")),
        "date_updated": clean_text(download.get("date_updated")),
        "access_level": access_level_for_download(
            clean_text(download.get("download_access")), license_label
        ),
    }


def access_mechanism(download: dict[str, Any]) -> str:
    text = lower_text(download["requirements"])
    if "aspera" in text or "faspex" in text:
        return "Aspera"
    if "data retriever" in text:
        return "TCIA Data Retriever"
    if not download["url"]:
        return "metadata only"
    return "direct download"


def download_artifact_role(download: dict[str, Any]) -> str:
    if not download["url"]:
        return "metadata only"
    mechanism = access_mechanism(download)
    if mechanism == "TCIA Data Retriever":
        return "manifest"
    if mechanism == "Aspera":
        return "transfer package"
    return "data file"


def downstream_access_system(download: dict[str, Any]) -> str:
    text = lower_text(
        download["title"],
        download["url"],
        download["search_url"],
        download["metadata_url"],
        download["requirements"],
    )
    if "general.datacommons.cancer.gov" in text or "gc_manifest" in text:
        return "General Commons"
    if (
        "clinical.datacommons.cancer.gov" in text
        or "drs_metadata_manifest" in text
        or "ctdc" in text
    ):
        return "Clinical Translational Data Commons (CTDC)"
    mechanism = access_mechanism(download)
    if mechanism == "Aspera":
        return "Aspera"
    is_open = download["access_level"] in {"open", "open_noncommercial"}
    is_dicom = any(ft.casefold() == "dicom" for ft in download["file_types"])
    if mechanism == "TCIA Data Retriever" and is_open and is_dicom:
        return "Imaging Data Commons (IDC)"
    return ""


def search_system(download: dict[str, Any]) -> str:
    text = lower_text(download["search_url"])
    if not text:
        return ""
    if "pathdb.cancerimagingarchive.net" in text:
        return "PathDB"
    if "nbia.cancerimagingarchive.net" in text:
        return "NBIA Search"
    if "clinical.datacommons.cancer.gov" in text:
        return "Clinical Translational Data Commons (CTDC)"
    if "general.datacommons.cancer.gov" in text:
        return "General Commons"
    if "datacommons.cancer.gov" in text:
        return "NCI Cancer Data Commons"
    return ""


def content_size(download: dict[str, Any]) -> str:
    size = download["download_size"]
    if not size:
        return ""
    return f"{size} {download['download_size_unit'].upper()}".strip()


def file_name_from_url(url: str, fallback: str) -> str:
    if not url:
        return fallback
    path = urllib.parse.urlparse(url).path
    return urllib.parse.unquote(PurePosixPath(path).name) or fallback


_FORMATS_BY_SUFFIX = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".zip": "application/zip",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".tcia": "text/plain",
    ".nii": "application/octet-stream",
    ".gz": "application/gzip",
    ".svs": "image/tiff",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".dcm": "application/dicom",
}

_FORMATS_BY_FILE_TYPE = {
    "dicom": "application/dicom",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
    "json": "application/json",
    "pdf": "application/pdf",
    "svs": "image/tiff",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "nifti": "application/octet-stream",
}


def encoding_formats(url: str, file_types: list[str]) -> list[str]:
    suffix = PurePosixPath(urllib.parse.urlparse(url).path).suffix.casefold()
    if suffix in _FORMATS_BY_SUFFIX:
        return [_FORMATS_BY_SUFFIX[suffix]]
    formats = [
        _FORMATS_BY_FILE_TYPE[ft.casefold()]
        for ft in file_types
        if ft.casefold() in _FORMATS_BY_FILE_TYPE
    ]
    return dedupe(formats) or ["application/octet-stream"]


def _download_properties(download: dict[str, Any]) -> list[dict[str, Any]]:
    """The additionalProperty names the TCIA Data Retriever reads."""
    return present(
        property_value("TCIA download id", download["id"]),
        property_value("TCIA access level", download["access_level"]),
        property_value("TCIA download types", download["download_types"]),
        property_value("TCIA data types", download["data_types"]),
        property_value("TCIA file types", download["file_types"]),
        property_value("TCIA download artifact role", download_artifact_role(download)),
        property_value("TCIA represented payload size", content_size(download)),
        property_value("TCIA access mechanism", access_mechanism(download)),
        property_value(
            "TCIA downstream access system", downstream_access_system(download)
        ),
        property_value("TCIA search system", search_system(download)),
        property_value("TCIA search/access URL", download["search_url"]),
        property_value("TCIA download metadata", download["metadata_url"]),
        property_value("TCIA download requirements", download["requirements"]),
    )


def file_object(
    download: dict[str, Any], file_id: str, fallback_name: str
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "@type": "cr:FileObject",
        "@id": file_id,
        "name": download["title"] or file_name_from_url(download["url"], fallback_name),
        "contentUrl": download["url"],
        "encodingFormat": encoding_formats(download["url"], download["file_types"]),
        "conditionsOfAccess": conditions_of_access(download["access_level"]),
        "usageInfo": policy_usage_info(
            download["access_level"], download["license_label"], download["license_url"]
        ),
    }
    add_if_present(item, "description", download["description"])
    if download_artifact_role(download) == "data file":
        add_if_present(item, "contentSize", content_size(download))
    add_if_present(
        item, "license", download["license_url"] or download["license_label"]
    )
    add_if_present(item, "dateModified", download["date_updated"])
    add_if_present(item, "additionalProperty", _download_properties(download))
    return item


def field(
    recordset_id: str, name: str, data_type: str, is_array: bool = False
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "@type": "cr:Field",
        "@id": f"{recordset_id}/{name}",
        "dataType": data_type,
    }
    if is_array:
        item["isArray"] = True
    return item


def recordset(
    download: dict[str, Any],
    recordset_id: str,
    file_id: str | None,
    dataset_short_title: str,
) -> dict[str, Any]:
    """One RecordSet per download page, holding a single inline data row."""
    name_parts = [
        download["title"],
        "; ".join(download["download_types"]),
        "; ".join(download["data_types"]),
        "; ".join(download["file_types"]),
    ]
    name = next((part for part in name_parts if part), f"Download {download['id']}")
    fields: list[dict[str, Any]] = []
    row: dict[str, Any] = {}

    def add_field(
        field_name: str, data_type: str, value: Any, is_array: bool = False
    ) -> None:
        fields.append(field(recordset_id, field_name, data_type, is_array=is_array))
        row[f"{recordset_id}/{field_name}"] = value

    add_field("download_id", "sc:Text", download["id"])
    if download["url"]:
        add_field("download_url", "sc:URL", download["url"])
    if download["search_url"]:
        add_field("search_url", "sc:URL", download["search_url"])
    if file_id:
        add_field("file_object_id", "sc:Text", file_id)
    add_field("download_types", "sc:Text", download["download_types"], is_array=True)
    add_field("data_types", "sc:Text", download["data_types"], is_array=True)
    add_field("file_types", "sc:Text", download["file_types"], is_array=True)
    add_field("download_artifact_role", "sc:Text", download_artifact_role(download))
    add_field("access_mechanism", "sc:Text", access_mechanism(download))
    if downstream_access_system(download):
        add_field(
            "downstream_access_system", "sc:Text", downstream_access_system(download)
        )
    if search_system(download):
        add_field("search_system", "sc:Text", search_system(download))
    add_field("access_level", "sc:Text", download["access_level"])
    add_field("license_label", "sc:Text", download["license_label"])
    if download["license_url"]:
        add_field("license_url", "sc:URL", download["license_url"])
    for count_key in ("subjects", "studies", "series", "images"):
        count = int_value(download[count_key])
        if count is not None:
            add_field(count_key, "sc:Integer", count)
    if download["metadata_url"]:
        add_field("download_metadata", "sc:URL", download["metadata_url"])
    if download["requirements"]:
        add_field("download_requirements", "sc:Text", download["requirements"])

    return {
        "@type": "cr:RecordSet",
        "@id": recordset_id,
        "name": name,
        "description": (
            f"TCIA current download record {download['id']} for "
            f"{dataset_short_title}."
        ),
        "dataType": "sc:DataDownload",
        "key": {"@id": f"{recordset_id}/download_id"},
        "field": fields,
        "data": [row],
        "conditionsOfAccess": conditions_of_access(download["access_level"]),
        "usageInfo": policy_usage_info(
            download["access_level"], download["license_label"], download["license_url"]
        ),
    }


def source_image_access_object(
    download: dict[str, Any], access_id: str, fallback_name: str
) -> dict[str, Any]:
    """An analysis result's source-collection download, listed under isBasedOn.
    The TCIA Data Retriever offers these as opt-in."""
    item: dict[str, Any] = {
        "@type": "DataDownload",
        "@id": access_id,
        "name": download["title"] or file_name_from_url(download["url"], fallback_name),
        "contentUrl": download["url"],
        "encodingFormat": encoding_formats(download["url"], download["file_types"]),
        "conditionsOfAccess": conditions_of_access(download["access_level"]),
        "usageInfo": policy_usage_info(
            download["access_level"], download["license_label"], download["license_url"]
        ),
    }
    if download_artifact_role(download) == "data file":
        add_if_present(item, "contentSize", content_size(download))
    add_if_present(
        item, "license", download["license_url"] or download["license_label"]
    )
    add_if_present(item, "dateModified", download["date_updated"])
    properties = present(
        property_value("TCIA source image access row", True),
        property_value("TCIA subjects", download["subjects"]),
        property_value("TCIA studies", download["studies"]),
        property_value("TCIA series", download["series"]),
        property_value("TCIA images", download["images"]),
    )
    item["additionalProperty"] = _download_properties(download) + properties
    return item


# ----------------------------
# Dataset level
# ----------------------------


def organization() -> dict[str, str]:
    return {
        "@type": "Organization",
        "name": "The Cancer Imaging Archive",
        "url": TCIA_ORG_URL,
    }


def data_catalog() -> dict[str, Any]:
    return {
        "@type": "DataCatalog",
        "@id": TCIA_CATALOG_ID,
        "name": "The Cancer Imaging Archive",
        "url": TCIA_ORG_URL,
        "publisher": organization(),
    }


def context() -> dict[str, Any]:
    return {
        "@language": "en",
        "@vocab": "https://schema.org/",
        "arrayShape": "cr:arrayShape",
        "citeAs": "cr:citeAs",
        "column": "cr:column",
        "conformsTo": "dct:conformsTo",
        "containedIn": "cr:containedIn",
        "cr": "http://mlcommons.org/croissant/",
        "rai": "http://mlcommons.org/croissant/RAI/",
        "data": {"@id": "cr:data", "@type": "@json"},
        "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
        "dct": "http://purl.org/dc/terms/",
        "description": {"@container": "@language"},
        "equivalentProperty": "cr:equivalentProperty",
        "examples": {"@id": "cr:examples", "@type": "@json"},
        "extract": "cr:extract",
        "field": "cr:field",
        "fileProperty": "cr:fileProperty",
        "fileObject": "cr:fileObject",
        "fileSet": "cr:fileSet",
        "format": "cr:format",
        "includes": "cr:includes",
        "isArray": "cr:isArray",
        "isLiveDataset": "cr:isLiveDataset",
        "jsonPath": "cr:jsonPath",
        "key": "cr:key",
        "md5": "cr:md5",
        "name": {"@container": "@language"},
        "parentField": "cr:parentField",
        "path": "cr:path",
        "recordSet": "cr:recordSet",
        "references": "cr:references",
        "regex": "cr:regex",
        "repeated": "cr:repeated",
        "replace": "cr:replace",
        "samplingRate": "cr:samplingRate",
        "sc": "https://schema.org/",
        "separator": "cr:separator",
        "source": "cr:source",
        "subField": "cr:subField",
        "transform": "cr:transform",
        "odrl": "http://www.w3.org/ns/odrl/2/",
        "sdVersion": "cr:sdVersion",
    }


def page_field(page: dict[str, Any], page_type: str, name: str) -> Any:
    """Reads collection_<name> or result_<name> by page type."""
    prefix = "collection" if page_type == "collection" else "result"
    return page.get(f"{prefix}_{name}")


def dataset_access_level(downloads: list[dict[str, Any]]) -> str:
    levels = {download["access_level"] for download in downloads}
    if "controlled" in levels and levels - {"controlled"}:
        return "mixed"
    if "controlled" in levels:
        return "controlled"
    if "open_noncommercial" in levels:
        return "open_noncommercial"
    if levels == {"open"}:
        return "open"
    return "unknown"


def dataset_licenses(downloads: list[dict[str, Any]]) -> list[str]:
    return dedupe(
        [download["license_url"] or download["license_label"] for download in downloads]
    )


def dataset_keywords(
    page: dict[str, Any], page_type: str, short_title: str
) -> list[str]:
    values = [short_title, PAGE_TYPES[page_type]]
    for key in ("data_types", "cancer_types", "cancer_locations", "species"):
        values.extend(as_list(page.get(key)))
    return dedupe(values)


def dataset_description(page: dict[str, Any], page_type: str, title: str) -> str:
    for name in ("abstract", "summary"):
        text = clean_text(page_field(page, page_type, name))
        if text:
            return text
    return f"TCIA metadata record for {title}."


def citation_text(title: str, doi: str, release: ReleaseInfo) -> str:
    year = (
        str(release.first_release_date.year) if release.first_release_date else "n.d."
    )
    url = doi_url(doi)
    if url:
        return f"{title}. The Cancer Imaging Archive. {year}. {url}"
    return f"{title}. The Cancer Imaging Archive. {year}."


def _download_entries(
    downloads: list[dict[str, Any]], short_title: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A FileObject (when the page has a URL) and a RecordSet per download.
    IDs come from the WordPress post ID, so they stay stable across releases --
    the retriever selects components by them."""
    distribution: list[dict[str, Any]] = []
    recordsets: list[dict[str, Any]] = []
    for index, download in enumerate(downloads):
        base = slugify(download["id"], f"download-{index + 1}")
        file_id = None
        if download["url"]:
            file_id = f"file-{base}"
            distribution.append(
                file_object(download, file_id, f"{short_title}-download-{index + 1}")
            )
        recordsets.append(recordset(download, f"download-{base}", file_id, short_title))
    return distribution, recordsets


def _source_entries(
    page: dict[str, Any], source_downloads: list[dict[str, Any]], short_title: str
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {"@type": "Dataset", "name": name} for name in as_list(page.get("collections"))
    ]
    for index, download in enumerate(source_downloads):
        base = slugify(download["id"], f"source-image-access-{index + 1}")
        entries.append(
            source_image_access_object(
                download,
                f"source-image-access-{base}",
                f"{short_title}-source-image-access-{index + 1}",
            )
        )
    return entries


def build_croissant(
    page: dict[str, Any],
    page_type: str,
    downloads: list[dict[str, Any]],
    release: ReleaseInfo,
    source_downloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Builds the Croissant document for one dataset release.

    page_type is the wp_object_type of the dataset's page: "collection" or
    "analysis_result". source_downloads only applies to an analysis result."""
    if page_type not in PAGE_TYPES:
        raise ValueError(f"Unsupported page type: {page_type}")

    short_title = clean_text(page_field(page, page_type, "short_title"))
    title = clean_text(page_field(page, page_type, "title")) or short_title
    doi = clean_text(page_field(page, page_type, "doi"))
    link = clean_text(page.get("view_url"))

    normalized = [normalize_download(download) for download in downloads]
    sources = [normalize_download(download) for download in source_downloads or []]
    access_level = dataset_access_level(normalized)
    distribution, recordsets = _download_entries(normalized, short_title)

    doc: dict[str, Any] = {
        "@context": context(),
        "@type": "sc:Dataset",
        "@id": doi_url(doi) or f"{link.rstrip('/')}/#dataset",
        "conformsTo": CROISSANT_CONFORMS_TO,
        "name": title,
        "alternateName": short_title,
        "description": dataset_description(page, page_type, title),
        "url": link,
        "creator": organization(),
        "publisher": organization(),
        "includedInDataCatalog": data_catalog(),
        "license": dataset_licenses(normalized) or [TCIA_DATA_USAGE_POLICY_URL],
        "citeAs": citation_text(title, doi, release),
        "keywords": dataset_keywords(page, page_type, short_title),
        "sdPublisher": organization(),
        "isLiveDataset": True,
        "version": str(release.release_number),
        "conditionsOfAccess": conditions_of_access(access_level),
        "usageInfo": policy_usage_info(access_level),
        "distribution": distribution,
        "recordSet": recordsets,
    }
    if page_type == "analysis_result":
        add_if_present(doc, "isBasedOn", _source_entries(page, sources, short_title))
    if doi:
        doc["sameAs"] = [doi_url(doi)]
    doc["identifier"] = present(
        property_value("TCIA short title", short_title),
        property_value("TCIA dataset type", PAGE_TYPES[page_type]),
        property_value("DOI", doi),
    )
    if release.first_release_date:
        doc["datePublished"] = release.first_release_date.isoformat()
    if release.release_date:
        doc["dateModified"] = release.release_date.isoformat()
    doc["additionalProperty"] = present(
        property_value("TCIA access level", access_level),
        property_value("TCIA subjects", clean_text(page.get("subjects"))),
        property_value("TCIA program", as_list(page.get("program"))),
        property_value(
            "TCIA downstream access systems",
            dedupe([downstream_access_system(d) for d in normalized]),
        ),
        property_value(
            "TCIA search systems", dedupe([search_system(d) for d in normalized])
        ),
    )
    return doc
