"""The Workflow page: the Perl @ActivityCategories steps with their buttons."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ...services import abc_definitions as defs
from ...services.operations import catalog
from .deps import Conn

router = APIRouter()


class WorkflowOperationOut(BaseModel):
    action: str
    caption: str
    special: str | None
    defined: bool  # the action names a spreadsheet_operation


class WorkflowQueryGroupOut(BaseModel):
    caption: str
    query_list_name: str


class WorkflowCategoryOut(BaseModel):
    id: str
    name: str
    description: str
    note: str | None
    operations: list[WorkflowOperationOut]
    query_groups: list[WorkflowQueryGroupOut]
    operation_picker: bool


def _category(raw: dict[str, Any], defined: set[str]) -> WorkflowCategoryOut:
    return WorkflowCategoryOut(
        id=raw["id"],
        name=raw["name"],
        description=raw.get("description", ""),
        note=raw.get("note"),
        operations=[
            WorkflowOperationOut(
                action=op.get("action", ""),
                caption=op.get("caption", ""),
                special=op.get("special") or None,
                defined=op.get("action", "") in defined,
            )
            for op in raw.get("operations", [])
        ],
        query_groups=[
            WorkflowQueryGroupOut(
                caption=q["caption"], query_list_name=q["query_list_name"]
            )
            for q in raw.get("queries", [])
            if q.get("operation") == "SelectQueryGroup"
        ],
        operation_picker=bool(raw.get("operation_picker")),
    )


@router.get("/categories", response_model=list[WorkflowCategoryOut])
async def categories(conn: Conn) -> list[WorkflowCategoryOut]:
    defined = await catalog.operation_names(conn)
    return [_category(raw, defined) for raw in defs.activity_categories()]
