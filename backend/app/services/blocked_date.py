import uuid
from datetime import date

from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.blocked_date import BlockedDate
from app.repositories.blocked_date import BlockedDateRepository
from app.schemas.blocked_date import BlockedDateCreate, BlockedDateUpdate

_OVERLAP_CONSTRAINT_NAME = "ex_blocked_dates_no_overlap"


class BlockedDateNotFoundError(NotFoundError):
    """Raised when no blocked date exists for the given id."""


class InvalidBlockedDateDatesError(ValidationError):
    """Raised when end_date is before start_date."""


class OverlappingBlockedDateError(ConflictError):
    """Raised when a blocked date's range overlaps another blocked date for the same apartment."""


def _conflict_error_for(exc: IntegrityError, *, default_message: str) -> ConflictError:
    """Translate an IntegrityError into a ConflictError with an accurate message.

    Same approach as services/rate_rule.py's _conflict_error_for: inspect the
    DB driver's diagnostics for the violated constraint name rather than
    importing a psycopg-specific exception type.
    """
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == _OVERLAP_CONSTRAINT_NAME:
        return OverlappingBlockedDateError(
            "This date range overlaps an existing blocked date for this apartment"
        )
    return ConflictError(default_message)


class BlockedDateService:
    """Business rules for BlockedDate. Delegates all persistence to BlockedDateRepository."""

    def __init__(self, repository: BlockedDateRepository) -> None:
        self.repository = repository

    @staticmethod
    def _validate_dates(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise InvalidBlockedDateDatesError("end_date must be on or after start_date")

    async def create_blocked_date(self, data: BlockedDateCreate) -> BlockedDate:
        self._validate_dates(data.start_date, data.end_date)

        blocked_date = BlockedDate(
            apartment_id=data.apartment_id,
            start_date=data.start_date,
            end_date=data.end_date,
            reason=data.reason,
        )
        try:
            return await self.repository.create(blocked_date)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise _conflict_error_for(
                exc, default_message="Could not create blocked date"
            ) from exc

    async def get_blocked_date(self, blocked_date_id: uuid.UUID) -> BlockedDate:
        blocked_date = await self.repository.get_by_id(blocked_date_id)
        if blocked_date is None:
            raise BlockedDateNotFoundError(f"Blocked date {blocked_date_id} not found")
        return blocked_date

    async def list_blocked_dates_by_apartment(self, apartment_id: uuid.UUID) -> list[BlockedDate]:
        blocked_dates = await self.repository.list_by_apartment(apartment_id)
        return list(blocked_dates)

    async def update_blocked_date(
        self, blocked_date_id: uuid.UUID, data: BlockedDateUpdate
    ) -> BlockedDate:
        blocked_date = await self.get_blocked_date(blocked_date_id)

        updates = data.model_dump(exclude_unset=True)
        new_start = updates.get("start_date", blocked_date.start_date)
        new_end = updates.get("end_date", blocked_date.end_date)
        self._validate_dates(new_start, new_end)

        for field, value in updates.items():
            setattr(blocked_date, field, value)

        try:
            return await self.repository.update(blocked_date)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise _conflict_error_for(
                exc, default_message="Could not update blocked date"
            ) from exc

    async def delete_blocked_date(self, blocked_date_id: uuid.UUID) -> None:
        # Unlike a rate rule, a blocked date protects no existing booking —
        # it can always be removed freely, no confirmed-booking check needed.
        blocked_date = await self.get_blocked_date(blocked_date_id)
        await self.repository.delete(blocked_date)
