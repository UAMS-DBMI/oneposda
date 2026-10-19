from papi.services.operations.background_query import background_query_plan
from papi.services.queries.catalog import QueryDetail


def detail(name: str, args: list[str]) -> QueryDetail:
    return QueryDetail(
        name=name,
        args=args,
        columns=["x"],
        schema="posda_files",
        tags=[],
        description="",
        query="select 1",
        is_select=True,
        runnable=True,
        not_runnable_reason=None,
    )


def test_plan_matches_the_perl_command_and_input_lines() -> None:
    plan = background_query_plan(
        detail("ImportEventsByDateRange", ["from", "to"]),
        ["2026-01-01", None],
        activity_id=7,
        notify="abc-dev",
    )
    assert plan.expanded_command == (
        'RunQueryInBackground.pl <?bkgrnd_id?> "7" ImportEventsByDateRange abc-dev'
    )
    assert plan.input_lines == ["2026-01-01", ""]
    assert plan.button_name == "background"
    assert plan.operation.worker_priority == 0


def test_plan_without_activity_sends_blank_activity_id() -> None:
    plan = background_query_plan(
        detail("PixelTypes", []), [], activity_id=None, notify="u"
    )
    assert (
        plan.expanded_command == 'RunQueryInBackground.pl <?bkgrnd_id?> "" PixelTypes u'
    )
    assert plan.input_lines == []
