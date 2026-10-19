from papi.services.operations.resolve import current_settings, resolve_args


def test_resolve_args_follows_the_perl_precedence() -> None:
    resolved = resolve_args(
        ["activity_id", "notify", "comment", "other"],
        prior_ss_args={"activity_id": 5},
        current_settings={"activity_id": 9, "notify": "abc-dev"},
        bindings={"comment": "hello", "activity_id": "1"},
    )
    assert resolved["activity_id"].value == "5"
    assert resolved["activity_id"].source == "from spreadsheet"
    assert resolved["notify"].source == "from current_settings"
    assert resolved["comment"].value == "hello"
    assert resolved["comment"].source == "from bindings"
    assert resolved["other"].value == ""
    assert resolved["other"].source == "not present"


async def test_current_settings_includes_latest_timepoint(conn) -> None:
    settings = await current_settings(
        conn, user="u", activity_id=1, extras={"from_timepoint_id": 3}
    )
    assert settings["notify"] == "u"
    assert settings["activity_id"] == 1
    assert isinstance(settings["activity_timepoint_id"], int)
    assert settings["from_timepoint_id"] == 3
    assert "activity_id" not in await current_settings(conn, user="u", activity_id=None)
