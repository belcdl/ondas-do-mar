import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.booking import BookingStatus
from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.schemas.booking import BookingCreate, BookingUpdate
from app.schemas.owner import OwnerCreate
from app.schemas.rate_rule import RateRuleCreate
from app.services.apartment import ApartmentNotFoundError, ApartmentService
from app.services.booking import (
    BookingNotFoundError,
    BookingService,
    InvalidBookingDatesError,
    InvalidBookingStatusTransitionError,
)
from app.services.owner import OwnerService
from app.services.owner_guard import InactiveOwnerError
from app.services.rate_rule import MinimumStayNotMetError, NoApplicableRateError, RateRuleService


def _owner_service(db_session: AsyncSession) -> OwnerService:
    return OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )


async def _make_owner(db_session: AsyncSession, **overrides: str | None):
    service = _owner_service(db_session)
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": None,
    }
    payload.update(overrides)
    return await service.create_owner(OwnerCreate(**payload))


async def _make_apartment(db_session: AsyncSession, owner_id: uuid.UUID, **overrides: str):
    service = ApartmentService(ApartmentRepository(db_session), OwnerRepository(db_session))
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    return await service.create_apartment(ApartmentCreate(**payload))


def _rate_rule_service(db_session: AsyncSession) -> RateRuleService:
    return RateRuleService(RateRuleRepository(db_session), BookingRepository(db_session))


def _booking_service(db_session: AsyncSession) -> BookingService:
    return BookingService(
        BookingRepository(db_session),
        ApartmentRepository(db_session),
        OwnerRepository(db_session),
        _rate_rule_service(db_session),
    )


async def _make_rate_rule(db_session: AsyncSession, apartment_id: uuid.UUID, **overrides: object):
    """Wide default range (today .. +400 days) so it covers whatever
    check_in/check_out offsets an individual test uses without every test
    having to pick dates that line up with a narrower rule."""
    service = _rate_rule_service(db_session)
    payload = {
        "apartment_id": apartment_id,
        "start_date": date.today(),
        "end_date": date.today() + timedelta(days=400),
        "price_per_night": Decimal("90.00"),
        "min_stay": 1,
    }
    payload.update(overrides)
    return await service.create_rate_rule(RateRuleCreate(**payload))


def _booking_payload(apartment_id: uuid.UUID, **overrides: object) -> BookingCreate:
    payload = {
        "apartment_id": apartment_id,
        "guest_full_name": "Jane Guest",
        "guest_email": "jane@example.com",
        "guest_phone": None,
        "guest_count": 2,
        "check_in_date": date.today() + timedelta(days=10),
        "check_out_date": date.today() + timedelta(days=15),
    }
    payload.update(overrides)
    return BookingCreate(**payload)


async def test_booking_lifecycle(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    created = await service.create_booking(_booking_payload(apartment.id))
    assert created.status == BookingStatus.PENDING
    assert created.owner_id == owner.id
    assert created.confirmation_code
    assert created.total_price == Decimal("450.00")
    assert created.currency == "EUR"

    fetched = await service.get_booking(created.id)
    assert fetched.guest_full_name == "Jane Guest"

    bookings = await service.list_bookings()
    assert any(b.id == created.id for b in bookings)

    updated = await service.update_booking(created.id, BookingUpdate(guest_count=3))
    assert updated.guest_count == 3

    confirmed = await service.confirm_booking(created.id)
    assert confirmed.status == BookingStatus.CONFIRMED
    assert confirmed.confirmed_at is not None

    confirmed_again = await service.confirm_booking(created.id)
    assert confirmed_again.confirmed_at == confirmed.confirmed_at

    completed = await service.complete_booking(created.id)
    assert completed.status == BookingStatus.COMPLETED

    with pytest.raises(InvalidBookingStatusTransitionError):
        await service.cancel_booking(created.id)

    with pytest.raises(BookingNotFoundError):
        await service.get_booking(uuid.uuid4())


async def test_create_booking_apartment_not_found(db_session: AsyncSession) -> None:
    service = _booking_service(db_session)
    with pytest.raises(ApartmentNotFoundError):
        await service.create_booking(_booking_payload(uuid.uuid4()))


async def test_create_booking_inactive_owner(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    owner_service = _owner_service(db_session)
    await owner_service.deactivate_owner(owner.id)

    service = _booking_service(db_session)
    with pytest.raises(InactiveOwnerError):
        await service.create_booking(_booking_payload(apartment.id))


async def test_create_booking_invalid_dates(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _booking_service(db_session)

    with pytest.raises(InvalidBookingDatesError):
        await service.create_booking(
            _booking_payload(
                apartment.id,
                check_in_date=date.today() + timedelta(days=10),
                check_out_date=date.today() + timedelta(days=5),
            )
        )


async def test_update_booking_invalid_dates(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)
    booking = await service.create_booking(_booking_payload(apartment.id))

    with pytest.raises(InvalidBookingDatesError):
        await service.update_booking(
            booking.id, BookingUpdate(check_out_date=booking.check_in_date)
        )


async def test_booking_owner_id_is_immutable_snapshot(db_session: AsyncSession) -> None:
    """Core historical-data guarantee: owner_id must never change after creation,
    even when the apartment is later reassigned to a different owner."""
    owner_a = await _make_owner(db_session)
    owner_b = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner_a.id)
    await _make_rate_rule(db_session, apartment.id)

    booking_service = _booking_service(db_session)
    booking = await booking_service.create_booking(_booking_payload(apartment.id))
    assert booking.owner_id == owner_a.id

    apartment_service = ApartmentService(ApartmentRepository(db_session), OwnerRepository(db_session))
    await apartment_service.update_apartment(apartment.id, ApartmentUpdate(owner_id=owner_b.id))

    unchanged = await booking_service.get_booking(booking.id)
    assert unchanged.owner_id == owner_a.id


async def test_cancel_completed_booking_fails(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking = await service.create_booking(_booking_payload(apartment.id))
    await service.confirm_booking(booking.id)
    await service.complete_booking(booking.id)

    with pytest.raises(InvalidBookingStatusTransitionError):
        await service.cancel_booking(booking.id)


async def test_complete_pending_booking_fails(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking = await service.create_booking(_booking_payload(apartment.id))
    with pytest.raises(InvalidBookingStatusTransitionError):
        await service.complete_booking(booking.id)


async def test_cancel_is_idempotent(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking = await service.create_booking(_booking_payload(apartment.id))
    cancelled = await service.cancel_booking(booking.id)
    cancelled_again = await service.cancel_booking(booking.id)
    assert cancelled_again.cancelled_at == cancelled.cancelled_at


# --- Sprint 5.3: overlap protection ------------------------------------------------


async def test_confirming_overlapping_booking_raises_conflict(db_session: AsyncSession) -> None:
    """The EXCLUDE constraint, not application logic, is what rejects this."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking_a = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=20),
            check_out_date=date.today() + timedelta(days=25),
        )
    )
    booking_b = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=22),
            check_out_date=date.today() + timedelta(days=27),
        )
    )

    await service.confirm_booking(booking_a.id)

    with pytest.raises(ConflictError):
        await service.confirm_booking(booking_b.id)


async def test_two_pending_overlapping_bookings_are_allowed(db_session: AsyncSession) -> None:
    """The constraint is partial (WHERE status = 'confirmed') — pending bookings never block."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking_a = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=30),
            check_out_date=date.today() + timedelta(days=35),
        )
    )
    booking_b = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=32),
            check_out_date=date.today() + timedelta(days=37),
        )
    )

    assert booking_a.status == BookingStatus.PENDING
    assert booking_b.status == BookingStatus.PENDING


async def test_cancelled_booking_no_longer_blocks_confirmation(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking_a = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=40),
            check_out_date=date.today() + timedelta(days=45),
        )
    )
    booking_b = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=42),
            check_out_date=date.today() + timedelta(days=47),
        )
    )

    await service.confirm_booking(booking_a.id)
    await service.cancel_booking(booking_a.id)

    confirmed_b = await service.confirm_booking(booking_b.id)
    assert confirmed_b.status == BookingStatus.CONFIRMED


async def test_non_overlapping_confirmed_bookings_allowed(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking_a = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=50),
            check_out_date=date.today() + timedelta(days=55),
        )
    )
    # check_out of A == check_in of B: adjacent, not overlapping ('[)' semantics).
    booking_b = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=55),
            check_out_date=date.today() + timedelta(days=60),
        )
    )

    await service.confirm_booking(booking_a.id)
    confirmed_b = await service.confirm_booking(booking_b.id)
    assert confirmed_b.status == BookingStatus.CONFIRMED


# --- Sprint 5.3: filters and confirmation-code lookup -------------------------------


async def test_list_bookings_filters(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking = await service.create_booking(
        _booking_payload(
            apartment.id,
            guest_email="Filter.Me@Example.com",
            check_in_date=date.today() + timedelta(days=60),
            check_out_date=date.today() + timedelta(days=65),
        )
    )

    by_apartment = await service.list_bookings(apartment_id=apartment.id)
    assert any(b.id == booking.id for b in by_apartment)

    by_owner = await service.list_bookings(owner_id=owner.id)
    assert any(b.id == booking.id for b in by_owner)

    by_status = await service.list_bookings(booking_status=BookingStatus.PENDING)
    assert any(b.id == booking.id for b in by_status)
    by_wrong_status = await service.list_bookings(booking_status=BookingStatus.CONFIRMED)
    assert all(b.id != booking.id for b in by_wrong_status)

    by_range = await service.list_bookings(
        check_in_from=date.today() + timedelta(days=59),
        check_in_to=date.today() + timedelta(days=61),
    )
    assert any(b.id == booking.id for b in by_range)
    by_wrong_range = await service.list_bookings(
        check_in_from=date.today() + timedelta(days=100)
    )
    assert all(b.id != booking.id for b in by_wrong_range)

    # case-insensitive
    by_email = await service.list_bookings(guest_email="filter.me@example.com")
    assert any(b.id == booking.id for b in by_email)


async def test_get_booking_by_confirmation_code(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    booking = await service.create_booking(_booking_payload(apartment.id))

    found = await service.get_booking_by_confirmation_code(booking.confirmation_code)
    assert found.id == booking.id

    # case-insensitive, whitespace-tolerant
    found_lower = await service.get_booking_by_confirmation_code(
        f"  {booking.confirmation_code.lower()}  "
    )
    assert found_lower.id == booking.id


async def test_get_booking_by_confirmation_code_not_found(db_session: AsyncSession) -> None:
    service = _booking_service(db_session)
    with pytest.raises(BookingNotFoundError):
        await service.get_booking_by_confirmation_code("NOPE0000")


# --- Server-computed pricing from rate_rules -----------------------------------------


async def test_create_booking_computes_total_from_single_rate_rule(
    db_session: AsyncSession,
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=date.today() + timedelta(days=100),
        end_date=date.today() + timedelta(days=110),
        price_per_night=Decimal("120.00"),
        min_stay=1,
    )
    service = _booking_service(db_session)

    booking = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=date.today() + timedelta(days=102),
            check_out_date=date.today() + timedelta(days=105),
        )
    )
    assert booking.total_price == Decimal("360.00")  # 3 nights * 120.00


async def test_create_booking_spanning_two_rate_rules_sums_per_night(
    db_session: AsyncSession,
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    check_in = date.today() + timedelta(days=200)
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in,
        end_date=check_in + timedelta(days=2),
        price_per_night=Decimal("100.00"),
        min_stay=1,
    )
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in + timedelta(days=3),
        end_date=check_in + timedelta(days=10),
        price_per_night=Decimal("150.00"),
        min_stay=1,
    )
    service = _booking_service(db_session)

    booking = await service.create_booking(
        _booking_payload(
            apartment.id,
            check_in_date=check_in,
            check_out_date=check_in + timedelta(days=5),
        )
    )
    # nights check_in..+2 at 100.00 (3 nights) plus +3..+4 at 150.00 (2 nights)
    assert booking.total_price == Decimal("600.00")


async def test_create_booking_night_with_no_rate_rule_raises(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    check_in = date.today() + timedelta(days=220)
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in,
        end_date=check_in + timedelta(days=1),
        price_per_night=Decimal("100.00"),
        min_stay=1,
    )
    service = _booking_service(db_session)

    with pytest.raises(NoApplicableRateError):
        await service.create_booking(
            _booking_payload(
                apartment.id,
                check_in_date=check_in,
                check_out_date=check_in + timedelta(days=3),
            )
        )


async def test_create_booking_below_minimum_stay_raises(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    check_in = date.today() + timedelta(days=230)
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in,
        end_date=check_in + timedelta(days=10),
        price_per_night=Decimal("100.00"),
        min_stay=5,
    )
    service = _booking_service(db_session)

    with pytest.raises(MinimumStayNotMetError):
        await service.create_booking(
            _booking_payload(
                apartment.id,
                check_in_date=check_in,
                check_out_date=check_in + timedelta(days=3),
            )
        )


async def test_booking_create_ignores_client_supplied_total_price(
    db_session: AsyncSession,
) -> None:
    """BookingCreate has no total_price field anymore — Pydantic's default
    extra="ignore" silently drops it rather than erroring, so this asserts
    explicitly on the resulting price to prove it's always server-computed,
    never a pass-through of whatever the caller sent."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    service = _booking_service(db_session)

    payload = _booking_payload(apartment.id, total_price=Decimal("999999.00"))
    assert "total_price" not in type(payload).model_fields

    booking = await service.create_booking(payload)
    assert booking.total_price == Decimal("450.00")
