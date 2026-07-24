"""One-off script to bootstrap the first admin user, bypassing the API.

There is no public endpoint to create the first User: POST /owners and
POST /owners/{id}/invite are both admin-only, so the very first admin has to
be inserted directly. Every admin/owner created after this one can go
through the normal API (POST /owners, then POST /owners/{id}/invite).

Usage:
    uv run python scripts/create_admin.py admin@ondasdomar.com "Sup3rSecret!" "Admin"
"""

import asyncio
import sys
from pathlib import Path

# Not installed as an editable package (package = false in pyproject.toml),
# so running this file directly puts scripts/ on sys.path instead of
# backend/. Add backend/ explicitly so `app` is importable regardless of
# how this is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows defaults to ProactorEventLoop, which psycopg's async driver cannot
# use. Only matters when running this script directly on native Windows
# (e.g. against a docker-compose Postgres exposed on localhost); inside the
# Linux backend container this branch never runs.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db.session import async_session_factory
from app.models.user import UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService


async def main(email: str, password: str, full_name: str) -> None:
    async with async_session_factory() as session:
        service = UserService(UserRepository(session))
        user = await service.create_user(
            UserCreate(email=email, password=password, full_name=full_name, role=UserRole.ADMIN)
        )
        print(f"Created admin {user.email} ({user.id})")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print('Usage: uv run python scripts/create_admin.py <email> "<password>" "<full name>"')
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
