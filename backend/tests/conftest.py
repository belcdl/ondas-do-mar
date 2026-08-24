import asyncio
import sys
import uuid
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService

settings = get_settings()
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TEST_DB_NAME = "ondas_do_mar_test"


def _create_test_database_if_missing() -> None:
    """CREATE DATABASE can't run inside a transaction, so this connects to
    the dev database (any existing database works as the throwaway
    'maintenance' connection — no separate 'postgres' database is assumed to
    exist) in AUTOCOMMIT and issues it directly. Already-exists is fine and
    silently ignored, so this is safe to run on every test session whether
    or not the database was provisioned before."""
    maintenance_engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        with maintenance_engine.connect() as conn:
            try:
                conn.execute(text(f"CREATE DATABASE {_TEST_DB_NAME}"))
            except ProgrammingError as exc:
                if "already exists" not in str(exc):
                    raise
    finally:
        maintenance_engine.dispose()


def _run_test_migrations() -> None:
    """Programmatic `alembic upgrade head` against the test database. Builds
    the Config directly (script_location + sqlalchemy.url) rather than
    shelling out to the alembic CLI or relying on env.py's own
    settings.database_url default, since environment variables aren't
    guaranteed to propagate consistently on Windows."""
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.test_database_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    """Runs once before the whole suite: provisions and migrates a database
    dedicated to tests (ondas_do_mar_test), fully isolated from whatever a
    human might have sitting in the dev database (ondas_do_mar) while
    poking at the app locally."""
    _create_test_database_if_missing()
    _run_test_migrations()


# Separate from app.db.session's engine, which points at the dev database
# (settings.database_url) — tests must never touch that one.
engine = create_async_engine(settings.test_database_url)


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
