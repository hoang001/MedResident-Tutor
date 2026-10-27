import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    field_validator,
)

from app.common.enums import UserRole
from app.core.config import get_settings


def login_email(value: str) -> str:
    value = value.strip().lower()
    try:
        return str(TypeAdapter(EmailStr).validate_python(value))
    except ValueError:
        settings = get_settings()
        if (
            settings.app_env == "development"
            and value.endswith(".local")
            and value == settings.seed_admin_email.strip().lower()
        ):
            # Validate syntax using a public suffix, retain the exact seed identity.
            TypeAdapter(EmailStr).validate_python(value[:-6] + ".example.com")
            return value
        raise ValueError("Invalid email address") from None


LoginEmail = Annotated[str, Field(min_length=3, max_length=254), AfterValidator(login_email)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=16384)


class LoginRequest(BaseModel):
    email: LoginEmail
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: LoginEmail
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
