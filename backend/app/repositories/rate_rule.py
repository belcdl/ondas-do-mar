import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rate_rule import RateRule


class RateRuleRepository:
    """Database access for RateRule. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, rate_rule: RateRule) -> RateRule:
        self.db.add(rate_rule)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(rate_rule)
        return rate_rule

    async def get_by_id(self, rate_rule_id: uuid.UUID) -> RateRule | None:
        return await self.db.get(RateRule, rate_rule_id)

    async def list_by_apartment(self, apartment_id: uuid.UUID) -> Sequence[RateRule]:
        stmt = (
            select(RateRule)
            .where(RateRule.apartment_id == apartment_id)
            .order_by(RateRule.start_date)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_covering_range(
        self, apartment_id: uuid.UUID, start_date: date, end_date: date
    ) -> Sequence[RateRule]:
        """Rate rules for apartment_id whose [start_date, end_date] span
        overlaps [start_date, end_date] (both inclusive) — i.e. every rule
        that prices at least one night in the given range."""
        stmt = (
            select(RateRule)
            .where(RateRule.apartment_id == apartment_id)
            .where(RateRule.start_date <= end_date)
            .where(RateRule.end_date >= start_date)
            .order_by(RateRule.start_date)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update(self, rate_rule: RateRule) -> RateRule:
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(rate_rule)
        return rate_rule

    async def delete(self, rate_rule: RateRule) -> None:
        await self.db.delete(rate_rule)
        await self.db.commit()
