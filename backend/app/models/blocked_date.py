import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, column, text
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.apartment import Apartment


class BlockedDate(Base):
    __tablename__ = "blocked_dates"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_blocked_dates_end_after_start"),
        # Same pattern as rate_rules' ex_rate_rules_no_overlap: inclusive on
        # both ends ('[]') since start_date/end_date are both blocked nights.
        ExcludeConstraint(
            (column("apartment_id"), "="),
            (
                func.daterange(column("start_date"), column("end_date"), text("'[]'")),
                "&&",
            ),
            using="gist",
            name="ex_blocked_dates_no_overlap",
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
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    apartment: Mapped["Apartment"] = relationship(back_populates="blocked_dates")
