import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ical_source import IcalSource


class IcalSourceRepository:
    """Database access for IcalSource. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, ical_source: IcalSource) -> IcalSource:
        self.db.add(ical_source)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(ical_source)
        return ical_source

    async def get_by_id(self, ical_source_id: uuid.UUID) -> IcalSource | None:
        return await self.db.get(IcalSource, ical_source_id)

    async def list_all(self) -> Sequence[IcalSource]:
        """Every IcalSource in the database, regardless of apartment — used
        by the scheduled sync job (app/core/scheduler.py), which has no
        single apartment to scope to."""
        stmt = select(IcalSource).order_by(IcalSource.created_at)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_by_apartment(self, apartment_id: uuid.UUID) -> Sequence[IcalSource]:
        stmt = (
            select(IcalSource)
            .where(IcalSource.apartment_id == apartment_id)
            .order_by(IcalSource.created_at)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update(self, ical_source: IcalSource) -> IcalSource:
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(ical_source)
        return ical_source

    async def delete(self, ical_source: IcalSource) -> None:
        await self.db.delete(ical_source)
        await self.db.commit()
