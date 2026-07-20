import os
import shutil
from collections.abc import AsyncIterator

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-at-least-thirty-two-characters"
os.environ["FILE_STORAGE_PATH"] = "./test-uploads"
os.environ["DEBUG"] = "false"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401, E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

test_engine = create_async_engine(os.environ["DATABASE_URL"])
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_db() -> AsyncIterator[AsyncSession]:
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_db


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    for path in ("test.db",):
        if os.path.exists(path):
            os.remove(path)
    shutil.rmtree("test-uploads", ignore_errors=True)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value
