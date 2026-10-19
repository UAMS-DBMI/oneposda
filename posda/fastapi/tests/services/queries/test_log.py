from papi.services.queries import log


async def test_query_invoked_and_finished_round_trip(conn) -> None:
    invoked_id = await log.query_invoked(
        conn, "ImportEvents", ["from", "to"], ["2026-01-01", None], "abc-test"
    )
    args = await conn.fetch(
        "select arg_index, arg_name, arg_value from dbif_query_args "
        "where query_invoked_by_dbif_id = $1 order by arg_index",
        invoked_id,
    )
    assert [tuple(a) for a in args] == [(0, "from", "2026-01-01"), (1, "to", None)]

    await log.query_finished(conn, invoked_id, 7)
    row = await conn.fetchrow(
        "select number_of_rows, query_end_time from query_invoked_by_dbif "
        "where query_invoked_by_dbif_id = $1",
        invoked_id,
    )
    assert row["number_of_rows"] == 7
    assert row["query_end_time"] is not None
