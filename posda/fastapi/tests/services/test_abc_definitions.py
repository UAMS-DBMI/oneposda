from papi.services import abc_definitions as defs


def test_chained_queries_load_with_arg_maps() -> None:
    chain = defs.chained_query("qc_1")
    assert chain is not None
    assert chain.from_query == "PixelTypes"
    assert chain.to_query == "FileIdByPixelType"
    assert chain.arg_map["bits_allocated"] == "bits_allocated"
    assert chain in defs.chained_from("PixelTypes")
    assert defs.chained_from("NoSuchQuery") == []


def test_processing_buttons_are_indexed_by_query() -> None:
    buttons = defs.processing_buttons_for("ImportEvents")
    assert any(
        b.operation == "CreateActivityTimepointFromImportEventId" for b in buttons
    )
    assert defs.processing_buttons_for("NoSuchQuery") == []


def test_column_buttons_apply_patterns_then_exact_matches() -> None:
    generic = {b.column: b for b in defs.column_buttons_for("AnyQueryAtAll")}
    assert "series_instance_uid" in generic  # query_pat '%' entries
    specific = {b.column: b for b in defs.column_buttons_for("MaskingStatus")}
    assert specific["image_equivalence_class_id"].obj == "MirabelleMaskVR"
    assert "series_instance_uid" in specific


def test_workflow_groups_keep_caption_and_query() -> None:
    group = defs.workflow_group("FindImportEvents")
    assert group is not None
    assert group.title.startswith("Suggested Queries")
    assert ("ImportEvents", "ImportEvents") in group.queries
    assert len(defs.activity_categories()) == 19
