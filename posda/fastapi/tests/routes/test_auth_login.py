"""Cookie login/logout. Redis and the database are stubbed; no server needed."""

from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from main import app
from papi.routes import auth
from papi.util import Database
from papi.util.password import encode

PASSWORD = "s3cret"


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def expire(self, key: str, seconds: int) -> None:
        pass

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


class FakeDatabase:
    async def fetch_one(self, query: str, parameters: list[object]) -> dict | list:
        if parameters == ["alice"]:
            return {
                "user_id": 1,
                "username": "alice",
                "full_name": "Alice",
                "hashed_password": encode(PASSWORD),
                "disabled": False,
            }
        return []


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeRedis]]:
    redis = FakeRedis()
    monkeypatch.setattr(auth, "get_redis_connection", lambda: redis)
    app.dependency_overrides[Database] = FakeDatabase
    try:
        yield TestClient(app), redis
    finally:
        app.dependency_overrides.pop(Database, None)


def test_login_sets_httponly_cookie(client: tuple[TestClient, FakeRedis]) -> None:
    http, redis = client

    response = http.post(
        "/auth/login", json={"username": "alice", "password": PASSWORD}
    )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("logintoken=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age" not in cookie
    assert "Secure" not in cookie
    token = http.cookies["logintoken"]
    assert redis.store[token] == "alice"


def test_login_marks_cookie_secure_behind_https(
    client: tuple[TestClient, FakeRedis],
) -> None:
    http, _ = client

    response = http.post(
        "/auth/login",
        json={"username": "alice", "password": PASSWORD},
        headers={"x-forwarded-proto": "https"},
    )

    assert "Secure" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "body",
    [{"username": "alice", "password": "wrong"}, {"username": "bob", "password": "x"}],
)
def test_bad_credentials(client: tuple[TestClient, FakeRedis], body: dict) -> None:
    http, _ = client
    response = http.post("/auth/login", json=body)
    assert response.status_code == 400
    assert response.json() == {"detail": "Incorrect username or password"}


def test_cookie_authenticates_and_logout_revokes(
    client: tuple[TestClient, FakeRedis],
) -> None:
    http, redis = client
    http.post("/auth/login", json={"username": "alice", "password": PASSWORD})

    assert http.get("/auth/users/me").json()["username"] == "alice"

    response = http.post("/auth/logout")

    assert response.status_code == 204
    assert redis.store == {}
    assert 'logintoken=""' in response.headers["set-cookie"]
    assert http.get("/auth/users/me").status_code == 401
