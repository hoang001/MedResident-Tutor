"""Verify Google credentials server-side; never trust client profile fields."""

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request, Response
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from starlette.concurrency import run_in_threadpool

from app.common.enums import UserRole
from app.core.config import Settings
from app.core.exceptions import AppError, AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password
from app.modules.auth.repository import UserRepository
from app.modules.users.models import User

COOKIE = "google_login_challenge"


def google_config(response: Response, settings: Settings) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if not settings.google_client_id:
        return {"client_id": None, "nonce": None}
    nonce = secrets.token_urlsafe(32)
    challenge = jwt.encode(
        {
            "nonce": nonce,
            "purpose": "google-login",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response.set_cookie(
        COOKIE,
        challenge,
        max_age=300,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        path="/api/v1/auth/google",
    )
    return {"client_id": settings.google_client_id, "nonce": nonce}


async def google_login(
    credential: str,
    request: Request,
    response: Response,
    repository: UserRepository,
    settings: Settings,
) -> str:
    if not settings.google_client_id:
        raise AppError("GOOGLE_NOT_CONFIGURED", "Google login is not configured", 503)
    try:
        challenge = jwt.decode(
            request.cookies.get(COOKIE, ""),
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp"]},
        )
        if challenge.get("purpose") != "google-login":
            raise ValueError("Invalid challenge")
        claims = await run_in_threadpool(
            id_token.verify_oauth2_token,
            credential,
            GoogleRequest(),
            settings.google_client_id,
        )
        if (
            not claims.get("sub")
            or not claims.get("nonce")
            or claims["nonce"] != challenge.get("nonce")
            or claims.get("email_verified") is not True
        ):
            raise ValueError("Invalid Google identity")
        email = str(claims.get("email", "")).lower()
        if not email.endswith("@gmail.com") and not claims.get("hd"):
            raise ValueError("Use a Gmail or Google Workspace account")
    except (ValueError, jwt.InvalidTokenError) as exc:
        raise AuthenticationError("Invalid or expired Google login; please try again") from exc
    except GoogleAuthError as exc:
        raise AppError("GOOGLE_UNAVAILABLE", "Google authentication is unavailable", 503) from exc
    user = await repository.get_by_google_subject(claims["sub"])
    if not user:
        if await repository.get_by_email(email):
            raise ConflictError(
                "GOOGLE_EMAIL_EXISTS", "Use your existing email and password to sign in"
            )
        user = await repository.add(
            User(
                email=email,
                google_subject=claims["sub"],
                hashed_password=hash_password(secrets.token_urlsafe(64)),
                full_name=str(claims.get("name") or email.split("@")[0])[:200],
                role=UserRole.LEARNER,
            )
        )
    if not user.is_active:
        raise AuthenticationError("Account is disabled")
    response.delete_cookie(COOKIE, path="/api/v1/auth/google")
    return create_access_token(str(user.id), settings)
