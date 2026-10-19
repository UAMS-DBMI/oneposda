"""Placeholders in operation command lines and input line formats.

``<name>`` in a command line is an argument the user supplies; ``<?name?>``
is a meta argument the worker fills in (``<?bkgrnd_id?>`` becomes the
subprocess_invocation_id). ``<name>`` in the input line format is a field
taken from each input row. Parsing mirrors ``BuildFieldsAndArgs`` in the
Perl app, except that duplicates are reported once and expansion replaces
every occurrence (the Perl substitution lacked ``/g``).
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

_PLACEHOLDER = re.compile(r"<([^<>]+)>")
_META = re.compile(r"^\?(.*)\?$")


@dataclass(frozen=True)
class Placeholders:
    args: list[str]
    meta_args: list[str]
    fields: list[str]


def _unique(names: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def parse(command_line: str | None, input_line_format: str | None) -> Placeholders:
    args: list[str] = []
    meta: list[str] = []
    for token in _PLACEHOLDER.findall(command_line or ""):
        match = _META.match(token)
        if match:
            meta.append(match.group(1))
        else:
            args.append(token)
    fields = _PLACEHOLDER.findall(input_line_format or "")
    return Placeholders(
        args=_unique(args), meta_args=_unique(meta), fields=_unique(fields)
    )


def expand_command(command_line: str, values: Mapping[str, str | None]) -> str:
    """Substitute ``<arg>`` for every arg in ``values``; meta args stay."""
    expanded = command_line
    for name, value in values.items():
        expanded = expanded.replace(f"<{name}>", "" if value is None else str(value))
    return expanded


def program_name(command_line: str) -> str | None:
    """The first word of the command line, as the Perl ``which`` check used."""
    head = command_line.strip().split(None, 1)
    return head[0] if head else None


def render_input_line(
    input_line_format: str, fields: Sequence[str], row: Mapping[str, object]
) -> str:
    line = input_line_format
    for field in fields:
        value = row.get(field)
        line = line.replace(f"<{field}>", "" if value is None else str(value))
    return line


def render_input_lines(
    input_line_format: str | None,
    fields: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> list[str]:
    if not input_line_format:
        return []
    return [render_input_line(input_line_format, fields, row) for row in rows]
