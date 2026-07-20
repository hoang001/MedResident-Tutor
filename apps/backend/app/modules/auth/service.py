from app.common.enums import UserRole
from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.repository import UserRepository
from app.modules.auth.schemas import LoginRequest, RegisterRequest
from app.modules.users.models import User


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def register(self, data: RegisterRequest) -> User:
        email = str(data.email).lower()
        if await self.repository.get_by_email(email):
            raise ConflictError("EMAIL_ALREADY_REGISTERED", "Email is already registered")
        user = User(
            email=email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=UserRole.LEARNER,
        )
        return await self.repository.add(user)

    async def login(self, data: LoginRequest) -> str:
        user = await self.repository.get_by_email(str(data.email).lower())
        if (
            not user
            or not user.is_active
            or not verify_password(data.password, user.hashed_password)
        ):
            raise AuthenticationError("Incorrect email or password")
        return create_access_token(str(user.id), self.settings)
