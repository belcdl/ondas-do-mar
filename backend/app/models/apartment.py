import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.apartment_photo import ApartmentPhoto
    from app.models.blocked_date import BlockedDate
    from app.models.booking import Booking
    from app.models.owner import Owner
    from app.models.rate_rule import RateRule


class Apartment(Base):
    __tablename__ = "apartments"
    __table_args__ = (
        CheckConstraint("max_guests > 0", name="ck_apartments_max_guests_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_guests: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, server_default=text("4")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["Owner"] = relationship(back_populates="apartments")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="apartment")
    rate_rules: Mapped[list["RateRule"]] = relationship(back_populates="apartment")
    blocked_dates: Mapped[list["BlockedDate"]] = relationship(back_populates="apartment")
    photos: Mapped[list["ApartmentPhoto"]] = relationship(back_populates="apartment")
