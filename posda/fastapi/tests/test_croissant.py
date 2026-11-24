"""Run from posda/fastapi/app:  pytest ../tests/test_croissant.py"""

from datetime import date
from typing import Any

import pytest

from papi.util.croissant import ReleaseInfo, build_croissant

RELEASE = ReleaseInfo(
    release_number=2,
    release_date=date(2026, 11, 20),
    first_release_date=date(2025, 3, 1),
)

MANIFEST_URL = "https://wp.example/wp-content/uploads/eval.tcia"


def collection_page() -> dict[str, Any]:
    """Collection 55832, as format_collection returns it (trimmed)."""
    return {
        "id": 55832,
        "view_url": "https://www.cancerimagingarchive.net/collection/pseudo/",
        "collection_doi": "10.7937/s17z-r072",
        "collection_title": "A DICOM dataset for evaluation of de-identification",
        "collection_short_title": "Pseudo-Clone-Test",
        "collection_abstract": "",
        "collection_downloads": [55836],
        "data_types": False,
        "species": ["Human"],
        "cancer_types": ["Various"],
        "program": ["MIDI"],
        "subjects": "21",
    }


def download_page(**overrides: Any) -> dict[str, Any]:
    """Download 55836, as format_download returns it, plus the resolved URL."""
    page = {
        "id": 55836,
        "title": "PSEUDO-CLONE-TEST-EVAL",
        "download_title": "Images - Evaluation dataset",
        "download_type": "Radiology Images",
        "data_type": ["PT", "MR", "CT"],
        "file_type": ["DICOM"],
        "download_access": "Public",
        "download_file": "56390",
        "download_url": "",
        "download_requirements": "Requires TCIA Data Retriever",
        "data_license": "CC BY 4.0",
        "search_url": "",
        "download_size": [],
        "download_size_unit": "",
        "subjects": [],
        "study_count": [],
        "series_count": [],
        "image_count": [],
        "date_updated": "2026-09-03",
        "description": "",
        "download_file_url": MANIFEST_URL,
        "download_metadata_url": "",
    }
    page.update(overrides)
    return page


def properties(item: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in item.get("additionalProperty", [])}


def test_dataset_fields_come_from_page_and_release() -> None:
    doc = build_croissant(collection_page(), "collection", [download_page()], RELEASE)

    assert doc["@id"] == "https://doi.org/10.7937/s17z-r072"
    assert doc["conformsTo"] == "http://mlcommons.org/croissant/1.1"
    assert doc["alternateName"] == "Pseudo-Clone-Test"
    assert doc["version"] == "2"
    assert doc["datePublished"] == "2025-03-01"
    assert doc["dateModified"] == "2026-11-20"
    assert doc["citeAs"].endswith("2025. https://doi.org/10.7937/s17z-r072")
    assert doc["license"] == ["https://creativecommons.org/licenses/by/4.0/"]
    assert "isBasedOn" not in doc


def test_retriever_download_becomes_manifest_row() -> None:
    doc = build_croissant(collection_page(), "collection", [download_page()], RELEASE)

    (file_object,) = doc["distribution"]
    assert file_object["@id"] == "file-55836"
    assert file_object["contentUrl"] == MANIFEST_URL
    assert file_object["encodingFormat"] == ["text/plain"]
    props = properties(file_object)
    assert props["TCIA download artifact role"] == "manifest"
    assert props["TCIA access mechanism"] == "TCIA Data Retriever"
    assert props["TCIA downstream access system"] == "Imaging Data Commons (IDC)"

    (record_set,) = doc["recordSet"]
    assert record_set["@id"] == "download-55836"
    assert record_set["name"] == "Images - Evaluation dataset"
    row = record_set["data"][0]
    assert row["download-55836/file_object_id"] == "file-55836"
    assert row["download-55836/access_level"] == "open"


def test_aspera_download_is_transfer_package() -> None:
    aspera = download_page(
        download_requirements="Requires IBM Aspera Connect",
        download_file_url="",
        download_url="https://faspex.example/public/package?context=x",
    )
    doc = build_croissant(collection_page(), "collection", [aspera], RELEASE)

    props = properties(doc["distribution"][0])
    assert props["TCIA download artifact role"] == "transfer package"


def test_download_url_used_when_no_file_attached() -> None:
    direct = download_page(
        download_requirements="",
        download_file_url="",
        download_url="https://wp.example/clinical.xlsx",
    )
    doc = build_croissant(collection_page(), "collection", [direct], RELEASE)

    file_object = doc["distribution"][0]
    assert file_object["contentUrl"] == "https://wp.example/clinical.xlsx"
    assert properties(file_object)["TCIA download artifact role"] == "data file"


def test_download_without_url_has_recordset_but_no_file() -> None:
    empty = download_page(download_file_url="", download_url="")
    doc = build_croissant(collection_page(), "collection", [empty], RELEASE)

    assert doc["distribution"] == []
    assert len(doc["recordSet"]) == 1


def test_limited_download_is_controlled_and_dataset_mixed() -> None:
    limited = download_page(id=55838, download_access="Limited")
    doc = build_croissant(
        collection_page(), "collection", [download_page(), limited], RELEASE
    )

    levels = [rs["data"][0][f"{rs['@id']}/access_level"] for rs in doc["recordSet"]]
    assert levels == ["open", "controlled"]
    assert properties(doc)["TCIA access level"] == "mixed"


def test_analysis_result_lists_source_downloads_under_is_based_on() -> None:
    page = {
        "view_url": "https://www.cancerimagingarchive.net/analysis-result/x/",
        "result_doi": "10.7937/abcd-1234",
        "result_title": "Segmentations",
        "result_short_title": "Segs",
        "collections": ["Pseudo-Clone-Test"],
    }
    doc = build_croissant(
        page,
        "analysis_result",
        [download_page(id=60001)],
        RELEASE,
        source_downloads=[download_page()],
    )

    names = [entry.get("name") for entry in doc["isBasedOn"]]
    assert names[0] == "Pseudo-Clone-Test"
    source = doc["isBasedOn"][1]
    assert source["@type"] == "DataDownload"
    assert source["@id"] == "source-image-access-55836"


def test_unknown_page_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_croissant(collection_page(), "download", [], RELEASE)
