"""Running a saved query in the background (Posda::BackgroundQuery).

The Perl popup did not go through ``spreadsheet_operation``: it queued
``RunQueryInBackground.pl <?bkgrnd_id?> "<activity_id>" <query_name> <notify>``
directly with the query's argument values as the worker's input lines. The
same command is built here as a synthetic operation so it takes the normal
launch path (spreadsheet record, subprocess_invocation, work row, Redis).
"""

from collections.abc import Sequence

from ..queries.catalog import QueryDetail
from .catalog import Operation
from .launch import LaunchPlan, make_plan
from .placeholders import parse

OPERATION_NAME = "RunQueryInBackground"
COMMAND_LINE = (
    'RunQueryInBackground.pl <?bkgrnd_id?> "<activity_id>" <query_name> <notify>'
)
INPUT_LINE_FORMAT = "<arg>"
BUTTON_NAME = "background"
WORKER_PRIORITY = 0


def background_query_operation() -> Operation:
    return Operation(
        operation_name=OPERATION_NAME,
        command_line=COMMAND_LINE,
        operation_type="background_process",
        input_line_format=INPUT_LINE_FORMAT,
        tags=["query"],
        can_chain=False,
        outdated=False,
        worker_priority=WORKER_PRIORITY,
        placeholders=parse(COMMAND_LINE, INPUT_LINE_FORMAT),
    )


def background_query_plan(
    query: QueryDetail,
    values: Sequence[str | None],
    *,
    activity_id: int | None,
    notify: str,
) -> LaunchPlan:
    """One input line per query argument, in the query's argument order."""
    rows = [{"arg": "" if v is None else v} for v in values]
    return make_plan(
        background_query_operation(),
        {
            "activity_id": "" if activity_id is None else str(activity_id),
            "query_name": query.name,
            "notify": notify,
        },
        rows,
        button_name=BUTTON_NAME,
    )
