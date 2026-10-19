from datetime import UTC, datetime, timedelta

import pytest

from papi.services.db_pools import DatabaseAlias, PoolRegistry
from papi.services.queries import catalog, log


def registry() -> PoolRegistry:
    return PoolRegistry(
        {"posda_files": DatabaseAlias("posda_files", "postgres", "posda_files")}
    )


async def test_search_matches_terms_in_each_field(conn) -> None:
    by_name = await catalog.search(conn, name="ImportEventsByDate")
    assert any(q.name == "ImportEventsByDateRange" for q in by_name)

    by_args = await catalog.search(conn, args="from, to", name="ImportEvents")
    assert by_args and all("from" in q.args and "to" in q.args for q in by_args)

    assert await catalog.search(conn) == []
    assert await catalog.search(conn, sql="'; drop table queries; --") == []


async def test_recent_and_frequent_follow_the_perl_rules(conn) -> None:
    user = "catalog-test-user"
    base = datetime(2026, 1, 1, tzinfo=UTC)
    history = [
        "ImportEvents",
        "ImportEvents",
        "ImportEventsByDateRange",
        "ImportEvents",
        "InsertActivityTimepointFile",
    ]
    for minutes, name in enumerate(history):
        await log.query_invoked(
            conn, name, [], [], user, started_at=base + timedelta(minutes=minutes)
        )

    lists = await catalog.recent_and_frequent(conn, user)
    # Most recent first, selects only, so the trailing insert is dropped.
    assert [q.name for q in lists.recent] == ["ImportEvents", "ImportEventsByDateRange"]
    # Everything frequent is already recent, so nothing is listed twice.
    assert lists.frequent == []


async def test_get_query_reports_runnability_and_links(conn) -> None:
    detail = await catalog.get_query(conn, "PixelTypes", registry())
    assert detail.runnable is True
    assert detail.is_select is True
    assert any(c.to_query == "FileIdByPixelType" for c in detail.chained_queries)

    with pytest.raises(catalog.QueryNotFound):
        await catalog.get_query(conn, "NoSuchQuery", registry())


async def test_get_query_explains_unconfigured_schema(conn) -> None:
    row = await conn.fetchrow(
        "select name from queries where schema = 'public' limit 1"
    )
    detail = await catalog.get_query(conn, row["name"], registry())
    assert detail.runnable is False
    assert "not configured" in (detail.not_runnable_reason or "")


async def test_workflow_groups_resolve_queries(conn) -> None:
    groups = await catalog.workflow_groups(conn)
    names = {g.name for g, _ in groups}
    assert "FindImportEvents" in names
    for group, found in groups:
        if group.name == "FindImportEvents":
            assert "ImportEvents" in found
