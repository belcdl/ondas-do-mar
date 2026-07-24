import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus


class BookingBase(BaseModel):
    apartment_id: uuid.UUID
    guest_full_name: str
    guest_email: str
    guest_phone: str | None = None
    guest_count: int = Field(gt=0)
    check_in_date: date
    check_out_date: date


class BookingCreate(BookingBase):
    pass


class BookingUpdate(BaseModel):
    guest_full_name: str | None = None
    guest_email: str | None = None
    guest_phone: str | None = None
    guest_count: int | None = Field(default=None, gt=0)
    check_in_date: date | None = None
    check_out_date: date | None = None
    # Admin-only — see api/bookings.py's update_booking for the role check.
    # An admin manually correcting a price after the fact is a legitimate
    # override; a guest or owner setting it is exactly what server-side
    # pricing (services/booking.py create_booking) closes off.
    total_price: Decimal | None = Field(default=None, gt=0)


class BookingRead(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    confirmation_code: str
    status: BookingStatus
    total_price: Decimal
    # Hardcoded to "EUR" server-side at creation (see services/booking.py
    # create_booking) — no multi-currency requirement exists anywhere in
    # the PRD yet. Read-only here; revisit if that changes.
    currency: str
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
