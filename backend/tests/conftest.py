import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db
from app.main import app


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
