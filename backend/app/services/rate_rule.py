import uuid
from datetime import date

from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.rate_rule import RateRule
from app.repositories.booking import BookingRepository
from app.repositories.rate_rule import RateRuleRepository
from app.schemas.rate_rule import RateRuleCreate, RateRuleUpdate

_OVERLAP_CONSTRAINT_NAME = "ex_rate_rules_no_overlap"


class RateRuleNotFoundError(NotFoundError):
    """Raised when no rate rule exists for the given id."""


class InvalidRateRuleDatesError(ValidationError):
    """Raised when end_date is before start_date."""


class OverlappingRateRuleError(ConflictError):
    """Raised when a rate rule's date range overlaps another rule for the same apartment."""


class RateRuleInUseError(ConflictError):
    """Raised when deleting a rate rule would leave a confirmed booking's stay unpriced."""


def _conflict_error_for(exc: IntegrityError, *, default_message: str) -> ConflictError:
    """Translate an IntegrityError into a ConflictError with an accurate message.

    Same approach as services/booking.py's _conflict_error_for: inspect the
    DB driver's diagnostics for the violated constraint name rather than
    importing a psycopg-specific exception type.
    """
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == _OVERLAP_CONSTRAINT_NAME:
        return OverlappingRateRuleError(
            "This date range overlaps an existing rate rule for this apartment"
        )
    return ConflictError(default_message)


class RateRuleService:
    """Business rules for RateRule. Delegates all persistence to RateRuleRepository."""

    def __init__(
        self, repository: RateRuleRepository, booking_repository: BookingRepository
    ) -> None:
        self.repository = repository
        self.booking_repository = booking_repository

    @staticmethod
    def _validate_dates(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise InvalidRateRuleDatesError("end_date must be on or after start_date")

    async def create_rate_rule(self, data: RateRuleCreate) -> RateRule:
        self._validate_dates(data.start_date, data.end_date)

        rate_rule = RateRule(
            apartment_id=data.apartment_id,
            start_date=data.start_date,
            end_date=data.end_date,
            price_per_night=data.price_per_night,
            min_stay=data.min_stay,
        )
        try:
            return await self.repository.create(rate_rule)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise _conflict_error_for(exc, default_message="Could not create rate rule") from exc

    async def get_rate_rule(self, rate_rule_id: uuid.UUID) -> RateRule:
        rate_rule = await self.repository.get_by_id(rate_rule_id)
        if rate_rule is None:
            raise RateRuleNotFoundError(f"Rate rule {rate_rule_id} not found")
        return rate_rule

    async def list_rate_rules_by_apartment(self, apartment_id: uuid.UUID) -> list[RateRule]:
        rate_rules = await self.repository.list_by_apartment(apartment_id)
        return list(rate_rules)

    async def update_rate_rule(self, rate_rule_id: uuid.UUID, data: RateRuleUpdate) -> RateRule:
        rate_rule = await self.get_rate_rule(rate_rule_id)

        updates = data.model_dump(exclude_unset=True)
        new_start = updates.get("start_date", rate_rule.start_date)
        new_end = updates.get("end_date", rate_rule.end_date)
        self._validate_dates(new_start, new_end)

        for field, value in updates.items():
            setattr(rate_rule, field, value)

        try:
            return await self.repository.update(rate_rule)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise _conflict_error_for(exc, default_message="Could not update rate rule") from exc

    async def delete_rate_rule(self, rate_rule_id: uuid.UUID) -> None:
        rate_rule = await self.get_rate_rule(rate_rule_id)
        has_confirmed_stay = await self.booking_repository.has_confirmed_overlap(
            rate_rule.apartment_id, rate_rule.start_date, rate_rule.end_date
        )
        if has_confirmed_stay:
            raise RateRuleInUseError(
                "Cannot delete a rate rule that covers a confirmed booking's stay"
            )
        await self.repository.delete(rate_rule)
