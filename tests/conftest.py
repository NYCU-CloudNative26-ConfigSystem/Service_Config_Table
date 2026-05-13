import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base, get_db
from main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture()
async def db_session():
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def auth_token(client: AsyncClient) -> str:
    """
    Obtain a JWT token for *testuser* / company *testcorp* via the
    convenience auth endpoint.
    """
    response = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "testuser",
            "password": "testpass",
            "client_id": "testcorp",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture()
async def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture()
async def other_token(client: AsyncClient) -> str:
    """Token for a second user (used to test ownership checks)."""
    response = await client.post(
        "/api/v1/auth/token",
        data={
            "username": "otheruser",
            "password": "otherpass",
            "client_id": "othercorp",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture()
async def other_headers(other_token: str) -> dict:
    return {"Authorization": f"Bearer {other_token}"}
