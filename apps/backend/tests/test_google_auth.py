import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.modules.users.models import User
from tests.conftest import TestSession


async def test_registration_persists_argon2_and_rejects_blank_name(client):
    email = f"hash-{uuid.uuid4()}@example.com"
    password = "RegistrationTest123!"
    body = {"email": email, "password": password, "full_name": "Test User"}
    response = await client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201
    assert "hashed_password" not in response.json()
    async with TestSession() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user.hashed_password.startswith("$argon2id$")
        assert verify_password(password, user.hashed_password)
        assert user.hashed_password != password
    body["full_name"] = "   "
    assert (await client.post("/api/v1/auth/register", json=body)).status_code == 422


async def test_google_login_validation_and_returning_user(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    config = (await client.get("/api/v1/auth/google/config")).json()
    subject = str(uuid.uuid4())
    claims = {
        "sub": subject,
        "email": f"test-{subject}@gmail.com",
        "email_verified": True,
        "nonce": config["nonce"],
        "name": "Google Test",
    }

    def verify(token, request, audience):
        assert audience == "test-client-id"
        if token == "invalid":
            raise ValueError("Invalid signature")
        return claims.copy()

    monkeypatch.setattr("app.modules.auth.google.id_token.verify_oauth2_token", verify)
    assert (
        await client.post("/api/v1/auth/google", json={"credential": "invalid"})
    ).status_code == 401
    claims["nonce"] = "wrong"
    assert (
        await client.post("/api/v1/auth/google", json={"credential": "valid"})
    ).status_code == 401
    claims["nonce"] = config["nonce"]
    result = await client.post("/api/v1/auth/google", json={"credential": "valid"})
    assert result.status_code == 200
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["role"] == "LEARNER"
    assert me["email"] == claims["email"]
    config = (await client.get("/api/v1/auth/google/config")).json()
    claims["nonce"] = config["nonce"]
    again = await client.post("/api/v1/auth/google", json={"credential": "valid"})
    assert again.status_code == 200
    async with TestSession() as session:
        users = list(await session.scalars(select(User).where(User.google_subject == subject)))
        assert len(users) == 1
        users[0].is_active = False
        await session.commit()
    config = (await client.get("/api/v1/auth/google/config")).json()
    claims["nonce"] = config["nonce"]
    assert (
        await client.post("/api/v1/auth/google", json={"credential": "valid"})
    ).status_code == 401


async def test_google_disabled_and_existing_email(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "")
    assert (await client.get("/api/v1/auth/google/config")).json()["client_id"] is None
    assert (await client.post("/api/v1/auth/google", json={"credential": "x"})).status_code == 503
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    email = f"existing-{uuid.uuid4()}@gmail.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Existing"},
    )
    config = (await client.get("/api/v1/auth/google/config")).json()
    monkeypatch.setattr(
        "app.modules.auth.google.id_token.verify_oauth2_token",
        lambda *args: {
            "sub": str(uuid.uuid4()),
            "email": email,
            "email_verified": True,
            "nonce": config["nonce"],
        },
    )
    result = await client.post("/api/v1/auth/google", json={"credential": "valid"})
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "GOOGLE_EMAIL_EXISTS"
