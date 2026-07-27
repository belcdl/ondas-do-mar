import uuid

from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment


class PaymentRepository:
    """Database access for Payment. No business rules live here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payment: Payment) -> Payment:
        self.db.add(payment)
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(payment)
        return payment

    async def get_by_booking_id(self, booking_id: uuid.UUID) -> Payment | None:
        result = await self.db.execute(
            select(Payment).where(Payment.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    async def get_by_checkout_session_id(self, checkout_session_id: str) -> Payment | None:
        result = await self.db.execute(
            select(Payment).where(Payment.stripe_checkout_session_id == checkout_session_id)
        )
        return result.scalar_one_or_none()

    async def update(self, payment: Payment) -> Payment:
        try:
            await self.db.commit()
        except (IntegrityError, DataError):
            await self.db.rollback()
            raise
        await self.db.refresh(payment)
        return payment
