import secrets
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError, ValidationError
from app.models.apartment import Apartment
from app.models.booking import Booking, BookingStatus
from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.apartment import ApartmentNotFoundError
from app.services.owner_guard import ensure_owner_is_active
from app.services.rate_rule import RateRuleService


class BookingNotFoundError(NotFoundError):
    """Raised when no booking exists for the given id."""


class InvalidBookingDatesError(ValidationError):
    """Raised when check_out_date is not after check_in_date."""


class InvalidBookingStatusTransitionError(BusinessRuleError):
    """Raised when a booking status transition isn't valid from its current status."""


def _generate_confirmation_code() -> str:
    return secrets.token_hex(4).upper()


_OVERLAP_CONSTRAINT_NAME = "ex_bookings_no_overlap_confirmed"


def _conflict_error_for(exc: IntegrityError, *, default_message: str) -> ConflictError:
    """Translate an IntegrityError into a ConflictError with an accurate message.

    Inspects the DB driver's diagnostics for the violated constraint name
    (psycopg exposes this via exc.orig.diag.constraint_name) rather than
    importing a psycopg-specific exception type, keeping this driver-agnostic
    at the type level while still being precise about *why* it failed.
    """
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == _OVERLAP_CONSTRAINT_NAME:
        return ConflictError("These dates are not available for this apartment")
    return ConflictError(default_message)


class BookingService:
    """Business rules for Booking. Delegates all persistence to BookingRepository."""

    def __init__(
        self,
        repository: BookingRepository,
        apartment_repository: ApartmentRepository,
        owner_repository: OwnerRepository,
        rate_rule_service: RateRuleService,
    ) -> None:
        self.repository = repository
        self.apartment_repository = apartment_repository
        self.owner_repository = owner_repository
        self.rate_rule_service = rate_rule_service

    async def _get_bookable_apartment(self, apartment_id: uuid.UUID) -> Apartment:
        apartment = await self.apartment_repository.get_by_id(apartment_id)
        if apartment is None:
            raise ApartmentNotFoundError(f"Apartment {apartment_id} not found")

        await ensure_owner_is_active(self.owner_repository, apartment.owner_id)

        return apartment

    @staticmethod
    def _validate_dates(check_in: date, check_out: date) -> None:
        if check_out <= check_in:
            raise InvalidBookingDatesError("check_out_date must be after check_in_date")

    async def _compute_total_price(
        self, apartment_id: uuid.UUID, check_in_date: date, check_out_date: date
    ) -> Decimal:
        nightly_prices = await self.rate_rule_service.price_stay(
            apartment_id, check_in_date, check_out_date
        )
        return sum((night.price for night in nightly_prices), Decimal("0.00"))

    async def create_booking(self, data: BookingCreate) -> Booking:
        self._validate_dates(data.check_in_date, data.check_out_date)
        apartment = await self._get_bookable_apartment(data.apartment_id)
        total_price = await self._compute_total_price(
            apartment.id, data.check_in_date, data.check_out_date
        )

        booking = Booking(
            apartment_id=apartment.id,
            owner_id=apartment.owner_id,
            confirmation_code=_generate_confirmation_code(),
            guest_full_name=data.guest_full_name,
            guest_email=data.guest_email,
            guest_phone=data.guest_phone,
            guest_count=data.guest_count,
            check_in_date=data.check_in_date,
            check_out_date=data.check_out_date,
            total_price=total_price,
            # Hardcoded: no multi-currency requirement exists anywhere in
            # the PRD yet. Revisit if/when Stripe Connect settlement needs
            # a real currency per booking.
            currency="EUR",
        )
        try:
            return await self.repository.create(booking)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise _conflict_error_for(
                exc, default_message="Could not create booking (confirmation code conflict)"
            ) from exc

    async def get_booking(self, booking_id: uuid.UUID) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise BookingNotFoundError(f"Booking {booking_id} not found")
        return booking

    async def get_booking_by_confirmation_code(self, confirmation_code: str) -> Booking:
        normalized_code = confirmation_code.strip().upper()
        booking = await self.repository.get_by_confirmation_code(normalized_code)
        if booking is None:
            raise BookingNotFoundError(
                f"Booking with confirmation code {normalized_code} not found"
            )
        return booking

    async def list_bookings(
        self,
        *,
        apartment_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        booking_status: BookingStatus | None = None,
        check_in_from: date | None = None,
        check_in_to: date | None = None,
        guest_email: str | None = None,
    ) -> list[Booking]:
        bookings = await self.repository.list_all(
            apartment_id=apartment_id,
            owner_id=owner_id,
            status=booking_status,
            check_in_from=check_in_from,
            check_in_to=check_in_to,
            guest_email=guest_email,
        )
        return list(bookings)

    async def update_booking(self, booking_id: uuid.UUID, data: BookingUpdate) -> Booking:
        booking = await self.get_booking(booking_id)

        updates = data.model_dump(exclude_unset=True)
        new_check_in = updates.get("check_in_date", booking.check_in_date)
        new_check_out = updates.get("check_out_date", booking.check_out_date)
        self._validate_dates(new_check_in, new_check_out)

        for field, value in updates.items():
            setattr(booking, field, value)

        try:
            return await self.repository.update(booking)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise _conflict_error_for(exc, default_message="Could not update booking") from exc

    async def confirm_booking(self, booking_id: uuid.UUID) -> Booking:
        booking = await self.get_booking(booking_id)
        if booking.status == BookingStatus.CONFIRMED:
            return booking
        if booking.status != BookingStatus.PENDING:
            raise InvalidBookingStatusTransitionError(
                f"Cannot confirm a booking with status '{booking.status.value}'"
            )
        booking.status = BookingStatus.CONFIRMED
        booking.confirmed_at = datetime.now(timezone.utc)
        try:
            return await self.repository.update(booking)
        except IntegrityError as exc:
            raise _conflict_error_for(exc, default_message="Could not confirm booking") from exc

    async def cancel_booking(self, booking_id: uuid.UUID) -> Booking:
        booking = await self.get_booking(booking_id)
        if booking.status == BookingStatus.CANCELLED:
            return booking
        if booking.status == BookingStatus.COMPLETED:
            raise InvalidBookingStatusTransitionError("Cannot cancel a completed booking")
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = datetime.now(timezone.utc)
        return await self.repository.update(booking)

    async def complete_booking(self, booking_id: uuid.UUID) -> Booking:
        booking = await self.get_booking(booking_id)
        if booking.status == BookingStatus.COMPLETED:
            return booking
        if booking.status != BookingStatus.CONFIRMED:
            raise InvalidBookingStatusTransitionError(
                f"Cannot complete a booking with status '{booking.status.value}'"
            )
        booking.status = BookingStatus.COMPLETED
        return await self.repository.update(booking)
