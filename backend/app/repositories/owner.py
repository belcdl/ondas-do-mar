import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.owner import Owner


class OwnerRepository:
    """Database access for Owner. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, owner: Owner) -> Owner:
        self.db.add(owner)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise
        await self.db.refresh(owner)
        return owner

    async def get_by_id(self, owner_id: uuid.UUID) -> Owner | None:
        return await self.db.get(Owner, owner_id)

    async def get_by_email(self, email: str) -> Owner | None:
        result = await self.db.execute(select(Owner).where(Owner.email == email))
        return result.scalar_one_or_none()

    async def list_all(self, *, include_inactive: bool = False) -> Sequence[Owner]:
        stmt = select(Owner).order_by(Owner.full_name)
        if not include_inactive:
            stmt = stmt.where(Owner.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update(self, owner: Owner) -> Owner:
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise
        await self.db.refresh(owner)
        return owner
