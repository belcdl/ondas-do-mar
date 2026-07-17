import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apartment import Apartment


class ApartmentRepository:
    """Database access for Apartment. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, apartment: Apartment) -> Apartment:
        self.db.add(apartment)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise
        await self.db.refresh(apartment)
        return apartment

    async def get_by_id(self, apartment_id: uuid.UUID) -> Apartment | None:
        return await self.db.get(Apartment, apartment_id)

    async def list_all(self, *, include_inactive: bool = False) -> Sequence[Apartment]:
        stmt = select(Apartment).order_by(Apartment.name)
        if not include_inactive:
            stmt = stmt.where(Apartment.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_by_owner(
        self, owner_id: uuid.UUID, *, include_inactive: bool = False
    ) -> Sequence[Apartment]:
        stmt = select(Apartment).where(Apartment.owner_id == owner_id).order_by(Apartment.name)
        if not include_inactive:
            stmt = stmt.where(Apartment.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update(self, apartment: Apartment) -> Apartment:
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise
        await self.db.refresh(apartment)
        return apartment
