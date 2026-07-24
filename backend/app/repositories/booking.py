import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus


class BookingRepository:
    """Database access for Booking. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, booking: Booking) -> Booking:
        self.db.add(booking)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(booking)
        return booking

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        return await self.db.get(Booking, booking_id)

    async def get_by_confirmation_code(self, confirmation_code: str) -> Booking | None:
        result = await self.db.execute(
            select(Booking).where(Booking.confirmation_code == confirmation_code)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        apartment_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        status: BookingStatus | None = None,
        check_in_from: date | None = None,
        check_in_to: date | None = None,
        guest_email: str | None = None,
    ) -> Sequence[Booking]:
        stmt = select(Booking).order_by(Booking.check_in_date)
        if apartment_id is not None:
            stmt = stmt.where(Booking.apartment_id == apartment_id)
        if owner_id is not None:
            stmt = stmt.where(Booking.owner_id == owner_id)
        if status is not None:
            stmt = stmt.where(Booking.status == status)
        if check_in_from is not None:
            stmt = stmt.where(Booking.check_in_date >= check_in_from)
        if check_in_to is not None:
            stmt = stmt.where(Booking.check_in_date <= check_in_to)
        if guest_email is not None:
            stmt = stmt.where(func.lower(Booking.guest_email) == guest_email.lower())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def has_confirmed_overlap(
        self, apartment_id: uuid.UUID, start_date: date, end_date: date
    ) -> bool:
        """True if a CONFIRMED booking for apartment_id has at least one
        stayed night inside [start_date, end_date] (inclusive on both ends,
        matching rate_rules' date semantics — check_out_date itself isn't a
        stayed night, hence the strict '>' below)."""
        stmt = (
            select(Booking.id)
            .where(Booking.apartment_id == apartment_id)
            .where(Booking.status == BookingStatus.CONFIRMED)
            .where(Booking.check_in_date <= end_date)
            .where(Booking.check_out_date > start_date)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update(self, booking: Booking) -> Booking:
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(booking)
        return booking
