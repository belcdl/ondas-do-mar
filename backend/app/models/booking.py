import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    column,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.apartment import Apartment
    from app.models.owner import Owner


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "check_out_date > check_in_date", name="ck_bookings_check_out_after_check_in"
        ),
        CheckConstraint("guest_count > 0", name="ck_bookings_guest_count_positive"),
        CheckConstraint("total_price > 0", name="ck_bookings_total_price_positive"),
        # Prevents two 'confirmed' bookings for the same apartment from having
        # overlapping date ranges, enforced atomically by Postgres itself — see
        # docs/decisions.md Decision 027 for why this replaces any app-level check.
        ExcludeConstraint(
            (column("apartment_id"), "="),
            (
                func.daterange(column("check_in_date"), column("check_out_date"), text("'[)'")),
                "&&",
            ),
            where=text("status = 'confirmed'"),
            using="gist",
            name="ex_bookings_no_overlap_confirmed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apartments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Snapshot of apartment.owner_id at creation time. Deliberately NOT kept in
    # sync with the apartment's current owner — see docs/decisions.md Decision 022.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    confirmation_code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    guest_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    guest_email: Mapped[str] = mapped_column(String(255), nullable=False)
    guest_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False)
    check_in_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_out_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=BookingStatus.PENDING,
        server_default=BookingStatus.PENDING.value,
    )
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    apartment: Mapped["Apartment"] = relationship(back_populates="bookings")
    owner: Mapped["Owner"] = relationship(back_populates="bookings")
