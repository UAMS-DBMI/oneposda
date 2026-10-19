"""Routes backing the ActivityBasedCuration web UI, mounted at /papi/v1/abc.

Every route requires a signed-in user with the ``launch`` permission on the
``ActivityBasedCuration`` app, the same check the Perl launcher applied.
"""

from fastapi import APIRouter, Depends

from . import (
    activities,
    background,
    downloads,
    files,
    inbox,
    me,
    operations,
    queries,
    query_runs,
    uploads,
    workflow,
)
from .deps import current_abc_user

router = APIRouter(
    tags=["ActivityBasedCuration"],
    dependencies=[Depends(current_abc_user)],
    responses={
        401: {"description": "User is not logged in"},
        403: {"description": "User may not use ActivityBasedCuration"},
    },
)
router.include_router(me.router, prefix="/me")
router.include_router(activities.router, prefix="/activities")
router.include_router(files.router, prefix="/files")
router.include_router(queries.router, prefix="/queries")
router.include_router(query_runs.router, prefix="/query-runs")
router.include_router(operations.router, prefix="/operations")
router.include_router(workflow.router, prefix="/workflow")
router.include_router(uploads.router, prefix="/uploads")
router.include_router(inbox.router, prefix="/inbox")
router.include_router(background.router, prefix="/background-jobs")
router.include_router(downloads.router, prefix="/downloads")
