import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocked_date import BlockedDate


class BlockedDateRepository:
    """Database access for BlockedDate. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, blocked_date: BlockedDate) -> BlockedDate:
        self.db.add(blocked_date)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(blocked_date)
        return blocked_date

    async def list_overlapping_range(
        self, apartment_id: uuid.UUID, start_date: date, end_date: date
    ) -> Sequence[BlockedDate]:
        """Blocked-date ranges for apartment_id that overlap [start_date,
        end_date] (both inclusive) — same overlap semantics as
        RateRuleRepository.list_covering_range."""
        stmt = (
            select(BlockedDate)
            .where(BlockedDate.apartment_id == apartment_id)
            .where(BlockedDate.start_date <= end_date)
            .where(BlockedDate.end_date >= start_date)
            .order_by(BlockedDate.start_date)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, blocked_date_id: uuid.UUID) -> BlockedDate | None:
        return await self.db.get(BlockedDate, blocked_date_id)

    async def list_by_apartment(self, apartment_id: uuid.UUID) -> Sequence[BlockedDate]:
        stmt = (
            select(BlockedDate)
            .where(BlockedDate.apartment_id == apartment_id)
            .order_by(BlockedDate.start_date)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update(self, blocked_date: BlockedDate) -> BlockedDate:
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(blocked_date)
        return blocked_date

    async def delete(self, blocked_date: BlockedDate) -> None:
        await self.db.delete(blocked_date)
        await self.db.commit()
