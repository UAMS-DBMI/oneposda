"""Pre-filling an operation's arguments, as ``Posda::NewerProcessPopup`` did.

Each argument is taken, in order, from the row or spreadsheet that launched
the operation, then from the current settings (selected activity, its latest
timepoint, the user as ``notify``, and any extras such as the compare
timepoints), then from the user's saved bindings, else left blank. The source
is kept so the UI can show where each value came from.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import asyncpg

Source = Literal[
    "from spreadsheet",
    "from current_settings",
    "from bindings",
    "not present",
    "entered",
]


@dataclass(frozen=True)
class ResolvedArg:
    value: str
    source: Source


def resolve_args(
    args: Sequence[str],
    *,
    prior_ss_args: Mapping[str, object] | None,
    current_settings: Mapping[str, object],
    bindings: Mapping[str, str | None],
) -> dict[str, ResolvedArg]:
    prior = prior_ss_args or {}
    resolved: dict[str, ResolvedArg] = {}
    for arg in args:
        if arg in prior:
            resolved[arg] = ResolvedArg(_text(prior[arg]), "from spreadsheet")
        elif arg in current_settings:
            resolved[arg] = ResolvedArg(
                _text(current_settings[arg]), "from current_settings"
            )
        elif arg in bindings:
            resolved[arg] = ResolvedArg(_text(bindings[arg]), "from bindings")
        else:
            resolved[arg] = ResolvedArg("", "not present")
    return resolved


def _text(value: object) -> str:
    return "" if value is None else str(value)


async def latest_timepoint_id(conn: asyncpg.Connection, activity_id: int) -> int | None:
    value = await conn.fetchval(
        "select max(activity_timepoint_id) from activity_timepoint where activity_id = $1",
        activity_id,
    )
    return int(value) if value is not None else None


async def current_settings(
    conn: asyncpg.Connection,
    *,
    user: str,
    activity_id: int | None,
    extras: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """``notify``, the selected activity and its latest timepoint, plus extras."""
    settings: dict[str, object] = {"notify": user}
    if activity_id is not None:
        settings["activity_id"] = activity_id
        settings["activity_timepoint_id"] = await latest_timepoint_id(conn, activity_id)
    if extras:
        settings.update(extras)
    return settings
