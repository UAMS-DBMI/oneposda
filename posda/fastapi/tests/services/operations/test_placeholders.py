from papi.services.operations.placeholders import (
    expand_command,
    parse,
    program_name,
    render_input_lines,
)


def test_parse_separates_args_meta_args_and_fields_in_order() -> None:
    result = parse(
        'AddFiles.pl <?bkgrnd_id?> <activity_id> "<comment>" <notify> <activity_id>',
        "<file_id>&<visibility>",
    )
    assert result.args == ["activity_id", "comment", "notify"]
    assert result.meta_args == ["bkgrnd_id"]
    assert result.fields == ["file_id", "visibility"]


def test_parse_handles_missing_formats() -> None:
    result = parse(None, None)
    assert (result.args, result.meta_args, result.fields) == ([], [], [])


def test_expand_replaces_every_occurrence_and_keeps_meta_args() -> None:
    command = 'Op.pl <?bkgrnd_id?> <activity_id> "<comment>" <activity_id>'
    expanded = expand_command(command, {"activity_id": "7", "comment": None})
    assert expanded == 'Op.pl <?bkgrnd_id?> 7 "" 7'
    assert program_name(command) == "Op.pl"
    assert program_name("   ") is None


def test_render_input_lines_substitutes_fields_per_row() -> None:
    lines = render_input_lines(
        "<file_id>&<note>",
        ["file_id", "note"],
        [{"file_id": 1, "note": None}, {"file_id": 2, "note": "x"}],
    )
    assert lines == ["1&", "2&x"]
    assert render_input_lines("", [], [{"a": 1}]) == []
