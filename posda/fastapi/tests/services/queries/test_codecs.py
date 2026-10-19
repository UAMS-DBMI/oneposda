from papi.services.queries.codecs import install_text_codecs


async def test_text_codecs_match_dbd_pg_rendering(conn) -> None:
    await install_text_codecs(conn)
    row = await conn.fetchrow("""
        select true as t, false as f, 1.50::numeric as n, 1.0::float8 as fl,
               timestamp with time zone '2026-08-26 21:48:29.5+00' as ts,
               interval '37.888997 seconds' as iv, date '2026-01-02' as d,
               array[1.5, 2.0]::numeric[] as arr, 7 as i
        """)
    assert (row["t"], row["f"]) == ("1", "0")
    assert row["n"] == "1.50"
    assert row["fl"] == "1"
    assert row["ts"].startswith("2026-08-26 21:48:29.5")
    assert row["iv"] == "00:00:37.888997"
    assert row["d"] == "2026-01-02"
    assert row["arr"] == ["1.5", "2.0"]
    assert row["i"] == 7
