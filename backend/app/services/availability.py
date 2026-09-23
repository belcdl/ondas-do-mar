import uuid
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

# Keeps a guest (or a scraper) from requesting an absurdly wide pricing
# calendar in one call.
_MAX_PRICING_CALENDAR_DAYS = 400


class InvalidAvailabilitySearchError(ValidationError):
    """Raised when check_out_date is not after check_in_date."""


class InvalidPricingCalendarRangeError(ValidationError):
    """Raised when to_date is before from_date, or the range spans more than
    _MAX_PRICING_CALENDAR_DAYS days."""


@dataclass(frozen=True)
class ApartmentAvailability:
    apartment: Apartment
    nights: int
    currency: str
    price_total: Decimal
    price_breakdown: list[NightlyPrice]


@dataclass(frozen=True)
class DayPricing:
    date: date
    price: Decimal | None
    available: bool


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

    @staticmethod
    def _validate_pricing_calendar_range(from_date: date, to_date: date) -> None:
        if to_date < from_date:
            raise InvalidPricingCalendarRangeError("to_date must be on or after from_date")
        span_days = (to_date - from_date).days + 1
        if span_days > _MAX_PRICING_CALENDAR_DAYS:
            raise InvalidPricingCalendarRangeError(
                f"Range cannot exceed {_MAX_PRICING_CALENDAR_DAYS} days"
            )

    async def get_pricing_calendar(
        self, apartment_id: uuid.UUID, from_date: date, to_date: date
    ) -> list[DayPricing]:
        """Day-by-day price and availability for apartment_id over
        [from_date, to_date] (both inclusive) — feeds the guest-facing
        calendar on the apartment page (Part 3).

        For each day: price is the covering RateRule's price_per_night, or
        None if no rule covers that day — the day is still returned (not
        skipped), so the frontend can render the gap. available is False if
        the day falls inside a CONFIRMED booking (check_out_date is
        exclusive, same semantics as has_confirmed_overlap elsewhere) or
        inside a BlockedDate (inclusive on both ends, per its model); True
        otherwise. A day can be priced and unavailable at once — price is
        informational and doesn't imply the day can be booked; a PENDING
        booking never affects availability, only CONFIRMED ones do.

        Reuses RateRuleService/BookingRepository/BlockedDateRepository as-is;
        doesn't duplicate any overlap logic.
        """
        self._validate_pricing_calendar_range(from_date, to_date)

        rate_rules = await self.rate_rule_service.list_rate_rules_covering_range(
            apartment_id, from_date, to_date
        )
        bookings = await self.booking_repository.list_confirmed_overlapping(
            apartment_id, from_date, to_date
        )
        blocked_dates = await self.blocked_date_repository.list_overlapping_range(
            apartment_id, from_date, to_date
        )

        days: list[DayPricing] = []
        day = from_date
        while day <= to_date:
            rule = next((r for r in rate_rules if r.start_date <= day <= r.end_date), None)
            is_booked = any(b.check_in_date <= day < b.check_out_date for b in bookings)
            is_blocked = any(bd.start_date <= day <= bd.end_date for bd in blocked_dates)
            days.append(
                DayPricing(
                    date=day,
                    price=rule.price_per_night if rule is not None else None,
                    available=not (is_booked or is_blocked),
                )
            )
            day += timedelta(days=1)

        return days
