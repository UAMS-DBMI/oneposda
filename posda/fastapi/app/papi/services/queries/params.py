"""Placeholder handling for saved queries.

Saved queries are written with DBI-style ``?`` placeholders. Perl passed every
argument as a string and let the database cast it. asyncpg is strictly typed,
so for Postgres the SQL is prepared once to learn what type each placeholder
was inferred as, then rewritten so the parameter is sent as text and cast
server-side (``$n::text::int4``), which reproduces DBI's behaviour exactly,
including its error for a blank integer. MySQL (pymysql) formats parameters
into the statement as strings already, so it only needs ``%s`` placeholders.

The tokenizer skips single-quoted strings, dollar-quoted strings, ``--`` line
comments and ``/* */`` block comments: a ``?`` inside any of those (jsonb's
``?`` operator in a comment, a literal ``'?'``) is not a placeholder. A naive
``replace("?", ...)`` is what the worker-side runner does and it breaks on
exactly those cases.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

Style = Literal["postgres", "mysql"]

_SELECT_LEADER = re.compile(
    r"^\s*(?:(?:--[^\n]*\n|/\*.*?\*/)\s*)*(?:select|with)\b", re.IGNORECASE | re.DOTALL
)
# Perl: /^\s*-*\s*select/i -- a leading "-- select" line forces select mode.
_FORCED_SELECT = re.compile(r"^\s*-+\s*select", re.IGNORECASE)


class PlaceholderError(ValueError):
    """The SQL could not be tokenized (an unterminated quote or comment)."""


@dataclass(frozen=True)
class Tokenized:
    sql: str
    placeholder_count: int


def is_select(sql: str) -> bool:
    """Whether a saved query returns rows.

    Perl only recognised a bare leading ``select`` (or a ``-- select`` line).
    Comments before the statement and ``with`` CTEs are also treated as
    selects here, since both are selects and otherwise ran as DML.
    """
    return bool(_FORCED_SELECT.match(sql) or _SELECT_LEADER.match(sql))


def _skip_single_quote(sql: str, i: int) -> int:
    """Index just past the string starting at sql[i] == "'" ('' escapes)."""
    i += 1
    while i < len(sql):
        if sql[i] == "'":
            if i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    raise PlaceholderError("unterminated string literal")


_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _skip_dollar_quote(sql: str, i: int) -> int | None:
    """Index past a dollar-quoted string at sql[i], or None if not one."""
    match = _DOLLAR_TAG.match(sql, i)
    if match is None:
        return None
    tag = match.group(0)
    end = sql.find(tag, match.end())
    if end < 0:
        raise PlaceholderError(f"unterminated dollar-quoted string {tag}")
    return end + len(tag)


def _skip_line_comment(sql: str, i: int) -> int:
    end = sql.find("\n", i)
    return len(sql) if end < 0 else end + 1


def _skip_block_comment(sql: str, i: int) -> int:
    end = sql.find("*/", i + 2)
    if end < 0:
        raise PlaceholderError("unterminated block comment")
    return end + 2


def tokenize(sql: str, style: Style) -> Tokenized:
    """Rewrite ``?`` placeholders for the driver, leaving everything else as is."""
    out: list[str] = []
    count = 0
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            j = _skip_single_quote(sql, i)
        elif ch == "$" and (j := _skip_dollar_quote(sql, i)) is not None:
            pass
        elif sql.startswith("--", i):
            j = _skip_line_comment(sql, i)
        elif sql.startswith("/*", i):
            j = _skip_block_comment(sql, i)
        elif ch == "?":
            count += 1
            out.append(f"${count}" if style == "postgres" else "%s")
            i += 1
            continue
        elif ch == "%" and style == "mysql":
            out.append("%%")
            i += 1
            continue
        else:
            out.append(ch)
            i += 1
            continue
        segment = sql[i:j]
        # pymysql formats the whole statement with %, quoted text included.
        out.append(segment.replace("%", "%%") if style == "mysql" else segment)
        i = j
    return Tokenized(sql="".join(out), placeholder_count=count)


def _cast_target(param_type: Any) -> str | None:
    """SQL type name a text parameter should be cast to, or None for text."""
    name = param_type.name
    if name in ("text", "unknown", "varchar", "bpchar"):
        return None
    schema = param_type.schema
    if schema in ("pg_catalog", "public"):
        return name
    return f"{schema}.{name}"


_PG_PLACEHOLDER = re.compile(r"\$(\d+)\b")


def with_text_casts(sql: str, param_types: list[Any]) -> str:
    """Rewrite ``$n`` to ``($n::text::<type>)`` per the prepared statement's types.

    Only ``$n`` tokens produced by ``tokenize`` are rewritten; they are
    matched positionally, so the caller must pass the tokenized SQL.
    """

    def rewrite(match: re.Match[str]) -> str:
        index = int(match.group(1))
        target = _cast_target(param_types[index - 1])
        if target is None:
            return f"(${index}::text)"
        return f"(${index}::text::{target})"

    return _PG_PLACEHOLDER.sub(rewrite, sql)


async def prepare_text_bound(conn: Any, sql: str) -> Any:
    """Prepare tokenized Postgres SQL so that every argument is passed as text."""
    first = await conn.prepare(sql)
    types = first.get_parameters()
    if not types:
        return first
    return await conn.prepare(with_text_casts(sql, list(types)))


def check_arg_count(expected: int, supplied: int) -> None:
    if expected != supplied:
        raise PlaceholderError(
            f"Binding error: {expected} required, {supplied} supplied"
        )
