import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, column, text
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.apartment import Apartment


class RateRule(Base):
    __tablename__ = "rate_rules"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_rate_rules_end_after_start"),
        CheckConstraint("price_per_night > 0", name="ck_rate_rules_price_per_night_positive"),
        CheckConstraint("min_stay > 0", name="ck_rate_rules_min_stay_positive"),
        # Prevents two rate rules for the same apartment from ever pricing the
        # same night, enforced atomically by Postgres itself — same pattern as
        # bookings' overlap constraint (see app/models/booking.py). Inclusive
        # on both ends ('[]') here, unlike bookings' '[)': a rate rule's
        # start_date and end_date are both priced nights, whereas a booking's
        # check_out_date is a checkout day, not a stayed night.
        ExcludeConstraint(
            (column("apartment_id"), "="),
            (
                func.daterange(column("start_date"), column("end_date"), text("'[]'")),
                "&&",
            ),
            using="gist",
            name="ex_rate_rules_no_overlap",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_night: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    min_stay: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    apartment: Mapped["Apartment"] = relationship(back_populates="rate_rules")
