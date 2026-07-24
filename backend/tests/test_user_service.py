import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token
from app.models.user import UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import InvalidCredentialsError, UserService


def _user_payload(**overrides: object) -> UserCreate:
    payload = {
        "email": f"user-{uuid.uuid4()}@example.com",
        "password": "Sup3rSecret!",
        "full_name": "Test User",
        "role": UserRole.OWNER,
    }
    payload.update(overrides)
    return UserCreate(**payload)


async def test_create_user_hashes_password(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    user = await service.create_user(_user_payload())
    assert user.hashed_password != "Sup3rSecret!"
    assert user.is_active is True


async def test_create_user_duplicate_email_raises_conflict(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    email = f"dup-{uuid.uuid4()}@example.com"
    await service.create_user(_user_payload(email=email))
    with pytest.raises(ConflictError):
        await service.create_user(_user_payload(email=email))


async def test_authenticate_success(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    created = await service.create_user(_user_payload(password="correct-horse"))
    authenticated = await service.authenticate(created.email, "correct-horse")
    assert authenticated.id == created.id


async def test_authenticate_wrong_password_raises_invalid_credentials(
    db_session: AsyncSession,
) -> None:
    service = UserService(UserRepository(db_session))
    created = await service.create_user(_user_payload(password="correct-horse"))
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(created.email, "wrong-password")


async def test_authenticate_nonexistent_email_raises_same_error(
    db_session: AsyncSession,
) -> None:
    """Same exception/message as a wrong password — no email enumeration."""
    service = UserService(UserRepository(db_session))
    with pytest.raises(InvalidCredentialsError, match="Incorrect email or password"):
        await service.authenticate("nobody@example.com", "whatever")


async def test_authenticate_inactive_user_raises_same_error(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    created = await service.create_user(_user_payload(password="correct-horse"))
    created.is_active = False
    db_session.add(created)
    await db_session.commit()

    with pytest.raises(InvalidCredentialsError, match="Incorrect email or password"):
        await service.authenticate(created.email, "correct-horse")


async def test_get_user_from_token_success(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    created = await service.create_user(_user_payload())
    token = create_access_token(subject=str(created.id))
    resolved = await service.get_user_from_token(token)
    assert resolved.id == created.id


async def test_get_user_from_token_garbage_token_raises(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    with pytest.raises(AuthenticationError):
        await service.get_user_from_token("not-a-real-token")


async def test_get_user_from_token_unknown_user_raises(db_session: AsyncSession) -> None:
    service = UserService(UserRepository(db_session))
    token = create_access_token(subject=str(uuid.uuid4()))
    with pytest.raises(AuthenticationError):
        await service.get_user_from_token(token)
