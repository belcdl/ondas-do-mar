import uuid

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Database access for User. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user: User, *, commit: bool = True) -> User:
        """commit=False stages the change (flush only) without ending the
        transaction — used by OwnerService.accept_invitation, which commits
        once at the end across three repositories so the whole operation is
        atomic. Every other caller keeps the default and behaves exactly as
        before."""
        self.db.add(user)
        try:
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def update(self, user: User) -> User:
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(user)
        return user
