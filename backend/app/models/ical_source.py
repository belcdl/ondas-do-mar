import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.apartment import Apartment


class IcalSource(Base):
    """An external platform's iCal feed (e.g. Booking.com, Airbnb) to sync
    availability from. Only the source itself is modeled here — the sync job
    that reads it and last_synced_at/last_sync_error are populated in a
    later step (see app/services/ical_export.py's docstring for step 1's
    scope: export only)."""

    __tablename__ = "ical_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    apartment: Mapped["Apartment"] = relationship(back_populates="ical_sources")
