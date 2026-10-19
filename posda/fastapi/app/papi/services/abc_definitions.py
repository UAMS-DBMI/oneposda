"""The ABC GUI's static definitions: query chaining, buttons and workflow groups.

The Perl app kept these as hashes in
``ActivityBasedCuration::{ButtonDefinition,WorkflowDefinition}``. They were
exported verbatim to ``papi/data/abc_definitions.json`` with::

    cd /home/posda/posdatools && perl -I ActivityBasedCuration/include \\
      -I Posda/include -I DbIf/include -MJSON -e '
      use ActivityBasedCuration::ButtonDefinition;
      use ActivityBasedCuration::WorkflowDefinition;
      print JSON->new->canonical->pretty->encode({
        QueryChaining => \\%ActivityBasedCuration::ButtonDefinition::QueryChaining,
        QueryChainColumnButtons => \\%ActivityBasedCuration::ButtonDefinition::QueryChainColumnButtons,
        QueryProcessingButtons => \\%ActivityBasedCuration::ButtonDefinition::QueryProcessingButtons,
        QueryToProcessingButton => \\%ActivityBasedCuration::ButtonDefinition::QueryToProcessingButton,
        WorkflowQueries => \\%ActivityBasedCuration::WorkflowDefinition::WorkflowQueries,
        ActivityCategories => \\@ActivityBasedCuration::WorkflowDefinition::ActivityCategories})'

Re-run that and replace the file if the Perl definitions change while both
GUIs are in service.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFINITIONS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "abc_definitions.json"
)


@dataclass(frozen=True)
class ChainedQuery:
    """A link from a row of ``from_query`` to the arg form of ``to_query``."""

    chained_query_id: str
    caption: str
    from_query: str
    to_query: str
    arg_map: dict[str, str]  # from column name -> to parameter name


@dataclass(frozen=True)
class ProcessingButton:
    """A table-level button that launches an operation over a result."""

    caption: str
    operation: str  # spreadsheet_operation name
    queries: frozenset[str]


@dataclass(frozen=True)
class ColumnButton:
    """A per-cell button; ``obj`` names the Perl popup class it opened."""

    button_id: str
    caption: str
    column: str
    obj: str
    query: str | None  # exact query name, or None when query_pat applies
    query_pattern: str | None
    col_to_param: dict[str, str]
    operation: str | None


@dataclass(frozen=True)
class WorkflowGroup:
    name: str
    title: str
    queries: tuple[tuple[str, str], ...]  # (caption, query name)


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    return json.loads(DEFINITIONS_PATH.read_text())


@lru_cache(maxsize=1)
def chained_queries() -> tuple[ChainedQuery, ...]:
    return tuple(
        ChainedQuery(
            chained_query_id=key,
            caption=entry["caption"],
            from_query=entry["from_query"],
            to_query=entry["to_query"],
            arg_map=dict(entry.get("arg_map", {})),
        )
        for key, entry in sorted(_raw()["QueryChaining"].items())
    )


def chained_from(query_name: str) -> list[ChainedQuery]:
    return [c for c in chained_queries() if c.from_query == query_name]


def chained_query(chained_query_id: str) -> ChainedQuery | None:
    for chain in chained_queries():
        if chain.chained_query_id == chained_query_id:
            return chain
    return None


@lru_cache(maxsize=1)
def processing_buttons() -> dict[str, tuple[ProcessingButton, ...]]:
    """Processing buttons keyed by the query they apply to."""
    by_query: dict[str, list[ProcessingButton]] = {}
    for entry in _raw()["QueryProcessingButtons"].values():
        operation = entry.get("spreadsheet_operation") or entry.get("operation")
        if not operation:
            continue
        button = ProcessingButton(
            caption=entry["caption"],
            operation=operation,
            queries=frozenset(entry.get("queries", {})),
        )
        for query_name in button.queries:
            by_query.setdefault(query_name, []).append(button)
    return {k: tuple(sorted(v, key=lambda b: b.caption)) for k, v in by_query.items()}


def processing_buttons_for(query_name: str) -> list[ProcessingButton]:
    return list(processing_buttons().get(query_name, ()))


def _sql_like_matches(pattern: str, value: str) -> bool:
    # The Perl sql_match only ever implemented the '%' wildcard.
    return pattern == "%" or pattern == value


@lru_cache(maxsize=1)
def column_buttons() -> tuple[ColumnButton, ...]:
    return tuple(
        ColumnButton(
            button_id=key,
            caption=entry["caption"],
            column=entry["col_name"],
            obj=entry["obj"],
            query=entry.get("query"),
            query_pattern=entry.get("query_pat"),
            col_to_param=dict(entry.get("col_to_param", {})),
            operation=entry.get("spreadsheet_operation") or entry.get("operation"),
        )
        for key, entry in sorted(_raw()["QueryChainColumnButtons"].items())
    )


def column_buttons_for(query_name: str) -> list[ColumnButton]:
    """Buttons for a query, exact matches overriding pattern matches per column.

    Mirrors ``get_popup_hash_new``: pattern entries apply first, then entries
    naming the query replace them column by column.
    """
    by_column: dict[str, ColumnButton] = {}
    for button in column_buttons():
        if button.query_pattern and _sql_like_matches(button.query_pattern, query_name):
            by_column[button.column] = button
    for button in column_buttons():
        if button.query == query_name:
            by_column[button.column] = button
    return [by_column[c] for c in sorted(by_column)]


@lru_cache(maxsize=1)
def workflow_groups() -> tuple[WorkflowGroup, ...]:
    groups = []
    for name, (title, queries) in sorted(_raw()["WorkflowQueries"].items()):
        groups.append(
            WorkflowGroup(
                name=name,
                title=title,
                queries=tuple((q["caption"], q["query"]) for q in queries),
            )
        )
    return tuple(groups)


def workflow_group(name: str) -> WorkflowGroup | None:
    for group in workflow_groups():
        if group.name == name:
            return group
    return None


def activity_categories() -> list[dict[str, Any]]:
    """The workflow page's step list, as the Perl @ActivityCategories."""
    return list(_raw()["ActivityCategories"])
