import pytest

fastapi = pytest.importorskip("fastapi")

from starlette.testclient import TestClient

from main import app
from papi.util import Database
from papi.routes import auth as auth_routes


class FakeDatabase:
    fetch_return = []
    fetch_one_return = []

    async def fetch(self, *args, **kwargs):
        return self.fetch_return

    async def fetch_one(self, *args, **kwargs):
        return self.fetch_one_return

    async def execute(self, *args, **kwargs):
        return None


async def fake_current_active_user():
    return auth_routes.User(user_id=1, username="tester", full_name="Test User")


@pytest.fixture
def client():
    app.dependency_overrides[Database] = FakeDatabase
    app.dependency_overrides[auth_routes.get_current_active_user] = (
        fake_current_active_user
    )
    # Note: not using the TestClient context manager on purpose -- entering it
    # would run the app lifespan and try to connect to a real database.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_auth_health(client):
    response = client.get("/auth/test")
    assert response.status_code == 200
    assert response.json() == {"message": "everything looks good"}


def test_collections_list(client):
    FakeDatabase.fetch_return = [
        {"collection": "TestCollection", "site": "TestSite", "file_count": 3},
    ]

    response = client.get("/v1/collections/")

    assert response.status_code == 200
    assert response.json() == [
        {"collection": "TestCollection", "site": "TestSite", "file_count": 3},
    ]
