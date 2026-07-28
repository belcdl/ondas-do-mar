import asyncio
import sys
import uuid

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.session import engine, get_db
from app.main import app
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService


@pytest_asyncio.fixture
async def db_session():
    """Bind a session to a single connection wrapped in an outer transaction.

    join_transaction_mode="create_savepoint" makes the app's own db.commit()
    calls release/restart a SAVEPOINT instead of really committing, so the
    outer transaction rollback below undoes everything the test did.
    """
    connection = await engine.connect()
    await connection.begin()

    session = AsyncSession(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )

    try:
        yield session
    finally:
        await session.close()
        await connection.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """HTTP client for the app with get_db overridden to the test transaction."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def auth_headers_for(user: User) -> dict[str, str]:
    """Build an Authorization header for any User — shared by every test file
    that needs to act as a specific admin/owner identity."""
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    service = UserService(UserRepository(db_session))
    return await service.create_user(
        UserCreate(
            email=f"admin-{uuid.uuid4()}@example.com",
            password="Sup3rSecret!",
            full_name="Test Admin",
            role=UserRole.ADMIN,
        )
    )


@pytest_asyncio.fixture
def admin_headers(admin_user: User) -> dict[str, str]:
    """Most fixture setup (creating owners/apartments/bookings) is easiest to
    do as an admin, since an admin can act on any owner_id. Tests that
    specifically exercise owner-vs-owner or owner-vs-admin authorization
    build their own owner-role users and headers via auth_headers_for()."""
    return auth_headers_for(admin_user)
