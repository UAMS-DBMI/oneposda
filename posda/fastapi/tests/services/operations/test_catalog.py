import pytest

from papi.services.operations import catalog
from papi.services.operations.placeholders import parse


def op(name: str, command: str, input_format: str) -> catalog.Operation:
    return catalog.Operation(
        operation_name=name,
        command_line=command,
        operation_type="background_process",
        input_line_format=input_format,
        tags=[],
        can_chain=False,
        outdated=False,
        worker_priority=0,
        placeholders=parse(command, input_format),
    )


def test_rank_candidates_requires_all_fields_and_sorts_by_matches() -> None:
    ops = [
        op("B", "b.pl <?bkgrnd_id?>", "<file_id>"),
        op("A", "a.pl <?bkgrnd_id?>", "<file_id>"),
        op("Two", "t.pl <?bkgrnd_id?>", "<file_id>&<series_instance_uid>"),
        op("NoInput", "n.pl <?bkgrnd_id?>", ""),
        op("Other", "o.pl <?bkgrnd_id?>", "<patient_id>"),
    ]
    ranked = catalog.rank_candidates(ops, ["series_instance_uid", "file_id", "extra"])
    assert [(c.operation.operation_name, c.matches) for c in ranked] == [
        ("Two", 2),
        ("A", 1),
        ("B", 1),
    ]


async def test_get_operation_parses_placeholders(conn) -> None:
    operation = await catalog.get_operation(conn, "AddFilesToTimepoint")
    assert operation.args == ["activity_id", "comment", "notify"]
    assert operation.meta_args == ["bkgrnd_id"]
    assert operation.fields == ["file_id"]
    assert operation.program == "AddFilesToTimepoint.pl"
    with pytest.raises(catalog.OperationNotFound):
        await catalog.get_operation(conn, "NoSuchOperation")


async def test_list_operations_filters_by_name_and_tag(conn) -> None:
    by_name = await catalog.list_operations(conn, name_like="addfilestotime")
    assert [o.operation_name for o in by_name] == ["AddFilesToTimepoint"]
    by_tag = await catalog.list_operations(conn, tags=["activity"])
    assert any(o.operation_name == "AddFilesToTimepoint" for o in by_tag)


def test_program_found_checks_script_dirs(tmp_path, monkeypatch) -> None:
    (tmp_path / "Posda" / "bin").mkdir(parents=True)
    (tmp_path / "Posda" / "bin" / "x.pl").write_text("")
    monkeypatch.setattr(catalog, "script_dirs", lambda: [tmp_path / "Posda" / "bin"])
    assert catalog.program_found(op("X", "x.pl <?bkgrnd_id?>", "")) is True
    assert catalog.program_found(op("Y", "y.pl <?bkgrnd_id?>", "")) is False
    assert catalog.program_found(op("Z", "", "")) is None
