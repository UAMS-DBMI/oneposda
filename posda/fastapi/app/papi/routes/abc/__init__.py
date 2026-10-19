"""Routes backing the ActivityBasedCuration web UI, mounted at /papi/v1/abc.

Every route requires a signed-in user with the ``launch`` permission on the
``ActivityBasedCuration`` app, the same check the Perl launcher applied.
"""

from fastapi import APIRouter, Depends

from . import activities, files, me
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
