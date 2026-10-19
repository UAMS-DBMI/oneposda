from fastapi import Depends, APIRouter, HTTPException, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.requests import Request
import uuid
import os
import logging

from ..util import Database
from ..util.password import is_valid
from ..util.redisqueue import get_redis_connection

router = APIRouter(
    tags=["Authentication"],
    responses={
        401:  {"description": "User is not logged in"},
    }
)

# disabling auto_error caues it to return None if unauthenticated
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/papi/auth/token",
                                     auto_error=False)

TOKEN_EXPIRE=(1 * 60 * 60) # 1 hour

logger = logging.getLogger(__name__)

# Failed sign-ins per username are counted in Redis; past the limit within
# the window the account is refused until the window passes.
LOGIN_FAILURE_LIMIT = int(os.environ.get("POSDA_LOGIN_FAILURE_LIMIT", "10"))
LOGIN_FAILURE_WINDOW = int(os.environ.get("POSDA_LOGIN_FAILURE_WINDOW", "300"))

# The Perl GUI sets this cookie from JavaScript; /login sets it server-side.
COOKIE_NAME = "logintoken"

API_SYSTEM_TOKEN = os.environ.get(
    'POSDA_API_SYSTEM_TOKEN',
    "nologinallowed"
)

class User(BaseModel):
    user_id: int
    username: str
    full_name: str = None
    disabled: bool = None

# Extend the User object to add a field
class UserInDB(User):
    hashed_password: str

async def get_user(db, username: str):
    user_dict = await get_user_from_database(db, username)
    if user_dict:
        return User(**user_dict)


async def decode_token(db, token):
    if token is None:
        return None

    redis_db = get_redis_connection()

    if token == API_SYSTEM_TOKEN:
        return await get_user(db, "system")
    
    username = redis_db.get(token)
    if username is None:
        return None

    redis_db.expire(token, TOKEN_EXPIRE)

    user = await get_user(db, username)
    return user


async def get_current_user(request: Request,
                           token: str = Depends(oauth2_scheme),
                           db: Database = Depends()):

    # If the token wasn't supplied via header...
    if token is None:
        # maybe it was supplied via cookie instead?
        token = request.cookies.get(COOKIE_NAME)

    user = await decode_token(db, token)
    if not user:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_user_from_database(db: Database, username: str):
    query = """
        select
            user_id,
            user_name as username,
            full_name,
            password as hashed_password,
            disabled
        from auth.users
        where user_name = $1
    """

    return await db.fetch_one(query, [username])

def _failure_key(username: str) -> str:
    return f"login_failures:{username.lower()}"


def _refuse_if_locked(username: str) -> None:
    failures = get_redis_connection().get(_failure_key(username))
    if failures is not None and int(failures) >= LOGIN_FAILURE_LIMIT:
        logger.warning("sign-in refused for %s: too many failures", username)
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts; try again later",
        )


def _record_failure(username: str) -> None:
    redis_db = get_redis_connection()
    key = _failure_key(username)
    if redis_db.incr(key) == 1:
        redis_db.expire(key, LOGIN_FAILURE_WINDOW)


async def authenticate_user(db: Database, username: str, password: str) -> UserInDB:
    """Return the user when the password matches, else 400.

    The same message is used for an unknown user and a wrong password so the
    response does not reveal which usernames exist. Repeated failures for a
    username are refused with 429 for LOGIN_FAILURE_WINDOW seconds.
    """
    _refuse_if_locked(username)
    user_dict = await get_user_from_database(db, username)
    if user_dict:
        user = UserInDB(**user_dict)
        if is_valid(user.hashed_password, password):
            get_redis_connection().delete(_failure_key(username))
            return user
    _record_failure(username)
    logger.info("failed sign-in for %s", username)
    raise HTTPException(status_code=400, detail="Incorrect username or password")


def issue_token(username: str) -> str:
    """Mint a session token and store it in Redis with the sliding expiry."""
    access_token = str(uuid.uuid4())
    get_redis_connection().set(access_token, username, ex=TOKEN_EXPIRE)
    return access_token


def _request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto")
    scheme = forwarded.split(",")[0].strip() if forwarded else request.url.scheme
    return scheme == "https"


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: Database = Depends()):
    user = await authenticate_user(db, form_data.username, form_data.password)
    access_token = issue_token(user.username)
    return {"access_token": access_token, "token_type": "bearer"}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", status_code=204)
async def login_with_cookie(body: LoginRequest, request: Request,
                            db: Database = Depends()) -> Response:
    """Sign in and set the session cookie server-side.

    The cookie is HttpOnly so page scripts never see the token, and it has no
    max-age: it lasts for the browser session while the Redis entry's sliding
    one-hour expiry decides whether it is still valid.
    """
    user = await authenticate_user(db, body.username, body.password)
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE_NAME,
        issue_token(user.username),
        path="/",
        httponly=True,
        samesite="lax",
        secure=_request_is_https(request),
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request,
                 token: str = Depends(oauth2_scheme)) -> Response:
    """Forget the session token and clear the cookie."""
    token = token or request.cookies.get(COOKIE_NAME)
    if token and token != API_SYSTEM_TOKEN:
        get_redis_connection().delete(token)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# These are just test functions
@router.get(
    "/users/me",
    response_model=User,
)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """
    Get the current logged in user
    """
    return current_user

@router.get("/test")
async def testpoint():
    return {"message":"everything looks good"}

# TODO: do we really want this here?
logged_in_user = Depends(get_current_active_user)
