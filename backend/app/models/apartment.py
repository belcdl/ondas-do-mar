import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.apartment_photo import ApartmentPhoto
    from app.models.blocked_date import BlockedDate
    from app.models.booking import Booking
    from app.models.ical_source import IcalSource
    from app.models.owner import Owner
    from app.models.rate_rule import RateRule


class AmenityType(str, enum.Enum):
    WIFI = "wifi"
    ELECTRIC_HEATING = "electric_heating"
    FAN = "fan"
    TV = "tv"
    EQUIPPED_KITCHEN = "equipped_kitchen"
    MICROWAVE = "microwave"
    TOASTER = "toaster"
    DISHWASHER = "dishwasher"
    COFFEE_MAKER = "coffee_maker"
    HAIR_DRYER = "hair_dryer"
    TERRACE = "terrace"
    ELEVATOR = "elevator"
    PETS_ALLOWED = "pets_allowed"
    NO_SMOKING = "no_smoking"
    SHARED_LAUNDRY = "shared_laundry"


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
    # Values are AmenityType members, stored as plain strings — validated at
    # the Pydantic schema layer (app.schemas.apartment) rather than with a
    # DB-level CHECK, since Postgres has no simple native way to constrain
    # every element of an array column against an enum.
    amenities: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )
    amenities_other: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    ical_sources: Mapped[list["IcalSource"]] = relationship(back_populates="apartment")
