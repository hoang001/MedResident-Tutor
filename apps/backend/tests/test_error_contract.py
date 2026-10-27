import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.main import app, http_error_handler


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": "do-not-echo-this"},
        {"email": "invalid@", "password": "do-not-echo-this"},
        {"email": {"sensitive": "do-not-echo-this"}, "password": "do-not-echo-this"},
    ],
)
async def test_login_validation_is_safe_json(client, body):
    response = await client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any(x["loc"][-1] == "email" for x in error["details"])
    assert "do-not-echo-this" not in response.text
    assert all(set(x) == {"loc", "msg", "type"} for x in error["details"])


async def test_invalid_json_does_not_echo_body(client):
    response = await client.post(
        "/api/v1/auth/login",
        content='{"password":"do-not-echo-this",',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "do-not-echo-this" not in response.text


async def test_http_exception_has_business_envelope():
    response = await http_error_handler(
        Request({"type": "http", "headers": []}),
        HTTPException(409, "Idempotency key reused with different input"),
    )
    error = json.loads(response.body)["error"]
    assert error["code"] == "HTTP_409"
    assert error["message"] == "Idempotency key reused with different input"


async def test_unexpected_exception_is_not_in_response_or_logs(client, caplog):
    async def broken():
        raise RuntimeError("do-not-echo-this learner answer password")

    original = list(app.router.routes)
    app.add_api_route("/__test_safe_error", broken)
    try:
        response = await client.get("/__test_safe_error")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "do-not-echo-this" not in response.text
        assert "do-not-echo-this" not in caplog.text
    finally:
        app.router.routes[:] = original
