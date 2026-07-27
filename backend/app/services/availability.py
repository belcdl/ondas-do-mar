from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.core.exceptions import ValidationError
from app.models.apartment import Apartment
from app.repositories.apartment import ApartmentRepository
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.booking import BookingRepository
from app.services.rate_rule import (
    MinimumStayNotMetError,
    NightlyPrice,
    NoApplicableRateError,
    RateRuleService,
)

# Hardcoded: no multi-currency requirement exists anywhere in the PRD yet —
# same rationale as services/booking.py's Booking.currency.
_CURRENCY = "EUR"


class InvalidAvailabilitySearchError(ValidationError):
    """Raised when check_out_date is not after check_in_date."""


@dataclass(frozen=True)
class ApartmentAvailability:
    apartment: Apartment
    nights: int
    currency: str
    price_total: Decimal
    price_breakdown: list[NightlyPrice]


class AvailabilityService:
    """Answers "which apartments are available for these dates, and at what
    price". Pure orchestration: every underlying rule (active apartments,
    capacity, existing bookings, blocked dates, rate rules/min_stay) is
    already enforced elsewhere (ApartmentRepository, BookingRepository,
    BlockedDateRepository, RateRuleService) and reused here as-is, so none of
    those rules are duplicated."""

    def __init__(
        self,
        apartment_repository: ApartmentRepository,
        booking_repository: BookingRepository,
        blocked_date_repository: BlockedDateRepository,
        rate_rule_service: RateRuleService,
    ) -> None:
        self.apartment_repository = apartment_repository
        self.booking_repository = booking_repository
        self.blocked_date_repository = blocked_date_repository
        self.rate_rule_service = rate_rule_service

    @staticmethod
    def _validate_dates(check_in_date: date, check_out_date: date) -> None:
        if check_out_date <= check_in_date:
            raise InvalidAvailabilitySearchError(
                "check_out_date must be after check_in_date (minimum stay is one night)"
            )

    async def search(
        self, check_in_date: date, check_out_date: date, guests: int
    ) -> list[ApartmentAvailability]:
        self._validate_dates(check_in_date, check_out_date)
        last_night = check_out_date - timedelta(days=1)

        results: list[ApartmentAvailability] = []
        for apartment in await self.apartment_repository.list_all():
            if apartment.max_guests < guests:
                continue

            has_confirmed_booking = await self.booking_repository.has_confirmed_overlap(
                apartment.id, check_in_date, last_night
            )
            if has_confirmed_booking:
                continue

            blocked_dates = await self.blocked_date_repository.list_overlapping_range(
                apartment.id, check_in_date, last_night
            )
            if blocked_dates:
                continue

            try:
                price_breakdown = await self.rate_rule_service.price_stay(
                    apartment.id, check_in_date, check_out_date
                )
            except (NoApplicableRateError, MinimumStayNotMetError):
                continue

            results.append(
                ApartmentAvailability(
                    apartment=apartment,
                    nights=len(price_breakdown),
                    currency=_CURRENCY,
                    price_total=sum((night.price for night in price_breakdown), Decimal("0.00")),
                    price_breakdown=price_breakdown,
                )
            )

        return results
