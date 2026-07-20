import uuid

from httpx import AsyncClient

from app.common.enums import UserRole
from app.core.security import hash_password
from app.modules.specialties.models import Specialty
from app.modules.users.models import User
from tests.conftest import TestSession


async def register_and_login(client: AsyncClient, email: str = "learner@example.com") -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Test Learner"},
    )
    assert response.status_code == 201
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123!"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def create_admin_token(client: AsyncClient) -> str:
    email = f"admin-{uuid.uuid4()}@example.com"
    async with TestSession() as session:
        session.add(
            User(
                email=email,
                hashed_password=hash_password("AdminPassword123!"),
                full_name="Test Admin",
                role=UserRole.ADMIN,
            )
        )
        session.add(Specialty(name=f"Specialty {uuid.uuid4()}", description=None))
        await session.commit()
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "AdminPassword123!"}
    )
    return response.json()["access_token"]


async def latest_specialty_id() -> str:
    from sqlalchemy import select

    async with TestSession() as session:
        specialty = await session.scalar(select(Specialty).order_by(Specialty.created_at.desc()))
        assert specialty
        return str(specialty.id)


async def test_health(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_ready(client: AsyncClient):
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_register_duplicate_login_and_me(client: AsyncClient):
    email = f"learner-{uuid.uuid4()}@example.com"
    token = await register_and_login(client, email)
    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": f"  {email.upper()} ", "password": "Password123!", "full_name": "Other"},
    )
    assert duplicate.status_code == 409
    bad_login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert bad_login.status_code == 401
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email
    assert "hashed_password" not in me.json()


async def test_topic_authorization(client: AsyncClient):
    learner_token = await register_and_login(client, f"topic-learner-{uuid.uuid4()}@example.com")
    admin_token = await create_admin_token(client)
    payload = {"specialty_id": await latest_specialty_id(), "name": "Demo API topic"}
    denied = await client.post(
        "/api/v1/topics",
        json=payload,
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    assert denied.status_code == 403
    created = await client.post(
        "/api/v1/topics", json=payload, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert created.status_code == 201
    assert created.json()["name"] == payload["name"]


async def test_invalid_upload_rejected(client: AsyncClient):
    token = await create_admin_token(client)
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("malware.exe", b"not executable", "application/octet-stream")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 415


async def test_valid_upload_returns_metadata_only(client: AsyncClient):
    token = await create_admin_token(client)
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.md", b"Development learning notes", "text/markdown")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["processing_status"] == "UPLOADED"
    assert body["file_size"] == len(b"Development learning notes")
    assert "storage_path" not in body
    assert "content" not in body


async def test_mock_rag_is_explicitly_ungrounded(client: AsyncClient):
    token = await register_and_login(client, f"rag-{uuid.uuid4()}@example.com")
    response = await client.post(
        "/api/v1/ai/rag/query",
        json={"question": "A development test question"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["grounded"] is False
    assert body["citations"] == []
    assert "not configured" in body["answer"]
    assert "diagnosis" in body["warning"]
