import uuid

from jwt import PyJWTError
from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate


class InvalidCredentialsError(AuthenticationError):
    """Raised when login credentials (email/password) are incorrect."""


class UserNotFoundError(NotFoundError):
    """Raised when no user exists for the given email."""


class UserService:
    """Business rules for User, including authentication. Delegates persistence to UserRepository."""

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def create_user(self, data: UserCreate) -> User:
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
        )
        try:
            return await self.repository.create(user)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError(f"User with email {data.email} already exists") from exc

    async def authenticate(self, email: str, password: str) -> User:
        """Verify email/password. Every failure mode (no such user, wrong
        password, inactive account) raises the exact same error — deliberately,
        so a caller probing this endpoint can't tell them apart. This is the
        direct fix for the email-enumeration gap the QA-1 audit found on
        POST /owners, applied here from the start rather than after the fact.
        """
        user = await self.repository.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Incorrect email or password")
        if not user.is_active:
            raise InvalidCredentialsError("Incorrect email or password")
        return user

    async def login(self, email: str, password: str) -> str:
        user = await self.authenticate(email, password)
        return create_access_token(subject=str(user.id))

    async def get_user_from_token(self, token: str) -> User:
        try:
            payload = decode_access_token(token)
        except PyJWTError as exc:
            raise AuthenticationError("Could not validate credentials") from exc

        subject = payload.get("sub")
        if subject is None:
            raise AuthenticationError("Could not validate credentials")

        try:
            user_id = uuid.UUID(subject)
        except ValueError as exc:
            raise AuthenticationError("Could not validate credentials") from exc

        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("Could not validate credentials")
        return user

    async def reset_password(self, email: str, new_password: str) -> User:
        """Admin-initiated password reset — the API-driven, auditable
        replacement for reaching into the database with scripts/reset_password.py."""
        user = await self.repository.get_by_email(email)
        if user is None:
            raise UserNotFoundError(f"User with email {email} not found")
        user.hashed_password = hash_password(new_password)
        return await self.repository.update(user)
