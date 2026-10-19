from dataclasses import dataclass

import pytest

from papi.services.queries.params import (
    PlaceholderError,
    check_arg_count,
    is_select,
    prepare_text_bound,
    tokenize,
    with_text_casts,
)


def test_tokenize_numbers_postgres_placeholders() -> None:
    result = tokenize("select * from t where a = ? and b = ?", "postgres")
    assert result.sql == "select * from t where a = $1 and b = $2"
    assert result.placeholder_count == 2


def test_tokenize_mysql_uses_percent_s_and_escapes_percent() -> None:
    result = tokenize("select * from t where a = ? and b like '%x%'", "mysql")
    assert result.sql == "select * from t where a = %s and b like '%%x%%'"
    assert result.placeholder_count == 1


def test_tokenize_skips_quotes_and_comments() -> None:
    sql = (
        "-- is it ?\n"
        "select '?' as q, /* jsonb ? op */ x from t\n"
        "where y = ? and z = $$a ? b$$ and w = $tag$ ? $tag$ and v = ?"
    )
    result = tokenize(sql, "postgres")
    assert result.placeholder_count == 2
    assert "$1" in result.sql and "$2" in result.sql
    assert "'?'" in result.sql
    assert "$$a ? b$$" in result.sql
    assert "-- is it ?\n" in result.sql


def test_tokenize_handles_doubled_quotes() -> None:
    result = tokenize("select 'it''s ?' where a = ?", "postgres")
    assert result.sql == "select 'it''s ?' where a = $1"


def test_tokenize_rejects_unterminated_literal() -> None:
    with pytest.raises(PlaceholderError):
        tokenize("select 'abc", "postgres")


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("select 1", True),
        ("  SELECT 1", True),
        ("-- select\ninsert into t values (1)", True),
        ("-- note\nselect 1", True),
        ("with x as (select 1) select * from x", True),
        ("insert into t values (?)", False),
        ("update t set a = 1", False),
    ],
)
def test_is_select(sql: str, expected: bool) -> None:
    assert is_select(sql) is expected


@dataclass
class FakeType:
    name: str
    schema: str = "pg_catalog"


def test_with_text_casts_rewrites_each_placeholder_by_type() -> None:
    sql = "select $1, $2, $3, $4"
    types = [
        FakeType("int4"),
        FakeType("text"),
        FakeType("text[]"),
        FakeType("mood", schema="app"),
    ]
    assert with_text_casts(sql, types) == (
        "select ($1::text::int4), ($2::text), ($3::text::text[]), ($4::text::app.mood)"
    )


def test_check_arg_count_matches_perl_message() -> None:
    check_arg_count(2, 2)
    with pytest.raises(PlaceholderError, match="2 required, 1 supplied"):
        check_arg_count(2, 1)


async def test_prepare_text_bound_passes_strings_for_any_type(conn) -> None:
    sql = tokenize(
        "select ?::int4 + 1 as n, ? = any(?) as member, ? as plain", "postgres"
    ).sql
    statement = await prepare_text_bound(conn, sql)
    row = await statement.fetchrow("41", "b", "{a,b}", "x")
    assert row["n"] == 42
    assert row["member"] is True
    assert row["plain"] == "x"


async def test_prepare_text_bound_reports_bad_integer_like_dbi(conn) -> None:
    import asyncpg

    sql = tokenize("select activity_id from activity where activity_id = ?", "postgres")
    statement = await prepare_text_bound(conn, sql.sql)
    with pytest.raises(asyncpg.PostgresError, match="invalid input syntax"):
        await statement.fetch("")
