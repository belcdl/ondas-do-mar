import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocked_date import BlockedDate
from app.repositories.apartment import ApartmentRepository
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.booking import BookingCreate
from app.schemas.owner import OwnerCreate
from app.schemas.rate_rule import RateRuleCreate
from app.services.apartment import ApartmentService
from app.services.availability import AvailabilityService, InvalidAvailabilitySearchError
from app.services.booking import BookingService
from app.services.owner import OwnerService
from app.services.rate_rule import RateRuleService


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


async def _make_apartment(db_session: AsyncSession, owner_id: uuid.UUID, **overrides: object):
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


async def _make_rate_rule(db_session: AsyncSession, apartment_id: uuid.UUID, **overrides: object):
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


def _booking_service(db_session: AsyncSession) -> BookingService:
    return BookingService(
        BookingRepository(db_session),
        ApartmentRepository(db_session),
        OwnerRepository(db_session),
        _rate_rule_service(db_session),
    )


async def _make_confirmed_booking(
    db_session: AsyncSession, apartment_id: uuid.UUID, check_in: date, check_out: date
):
    service = _booking_service(db_session)
    booking = await service.create_booking(
        BookingCreate(
            apartment_id=apartment_id,
            guest_full_name="Jane Guest",
            guest_email="jane@example.com",
            guest_count=2,
            check_in_date=check_in,
            check_out_date=check_out,
        )
    )
    return await service.confirm_booking(booking.id)


async def _make_blocked_date(
    db_session: AsyncSession, apartment_id: uuid.UUID, start_date: date, end_date: date
) -> BlockedDate:
    repository = BlockedDateRepository(db_session)
    return await repository.create(
        BlockedDate(apartment_id=apartment_id, start_date=start_date, end_date=end_date)
    )


def _availability_service(db_session: AsyncSession) -> AvailabilityService:
    return AvailabilityService(
        ApartmentRepository(db_session),
        BookingRepository(db_session),
        BlockedDateRepository(db_session),
        _rate_rule_service(db_session),
    )


async def test_free_apartment_is_available(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id, price_per_night=Decimal("120.00"))
    service = _availability_service(db_session)

    check_in = date.today() + timedelta(days=10)
    check_out = check_in + timedelta(days=3)
    results = await service.search(check_in, check_out, guests=2)

    assert len(results) == 1
    result = results[0]
    assert result.apartment.id == apartment.id
    assert result.nights == 3
    assert result.currency == "EUR"
    assert result.price_total == Decimal("360.00")
    assert [n.price for n in result.price_breakdown] == [Decimal("120.00")] * 3


async def test_apartment_with_confirmed_booking_is_excluded(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    check_in = date.today() + timedelta(days=20)
    check_out = check_in + timedelta(days=5)
    await _make_confirmed_booking(db_session, apartment.id, check_in, check_out)

    service = _availability_service(db_session)
    results = await service.search(check_in, check_out, guests=2)

    assert results == []


async def test_pending_booking_does_not_block_availability(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    booking_service = _booking_service(db_session)
    check_in = date.today() + timedelta(days=25)
    check_out = check_in + timedelta(days=5)
    await booking_service.create_booking(
        BookingCreate(
            apartment_id=apartment.id,
            guest_full_name="Jane Guest",
            guest_email="jane@example.com",
            guest_count=2,
            check_in_date=check_in,
            check_out_date=check_out,
        )
    )

    service = _availability_service(db_session)
    results = await service.search(check_in, check_out, guests=2)

    assert len(results) == 1
    assert results[0].apartment.id == apartment.id


async def test_apartment_with_blocked_dates_is_excluded(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=5)
    await _make_blocked_date(db_session, apartment.id, check_in, check_out - timedelta(days=1))

    service = _availability_service(db_session)
    results = await service.search(check_in, check_out, guests=2)

    assert results == []


async def test_apartment_below_minimum_stay_is_excluded(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    check_in = date.today() + timedelta(days=40)
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in,
        end_date=check_in + timedelta(days=10),
        min_stay=5,
    )

    service = _availability_service(db_session)
    results = await service.search(check_in, check_in + timedelta(days=2), guests=2)

    assert results == []


async def test_season_change_prices_each_night_from_its_own_rate_rule(
    db_session: AsyncSession,
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    check_in = date.today() + timedelta(days=50)
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in,
        end_date=check_in + timedelta(days=2),
        price_per_night=Decimal("100.00"),
    )
    await _make_rate_rule(
        db_session,
        apartment.id,
        start_date=check_in + timedelta(days=3),
        end_date=check_in + timedelta(days=10),
        price_per_night=Decimal("150.00"),
    )

    service = _availability_service(db_session)
    check_out = check_in + timedelta(days=5)
    results = await service.search(check_in, check_out, guests=2)

    assert len(results) == 1
    result = results[0]
    assert result.nights == 5
    assert [n.price for n in result.price_breakdown] == [
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("150.00"),
        Decimal("150.00"),
    ]
    # 3 nights * 100.00 + 2 nights * 150.00
    assert result.price_total == Decimal("600.00")


async def test_apartment_with_insufficient_capacity_is_excluded(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id, max_guests=2)
    await _make_rate_rule(db_session, apartment.id)

    service = _availability_service(db_session)
    check_in = date.today() + timedelta(days=60)
    results = await service.search(check_in, check_in + timedelta(days=3), guests=4)

    assert results == []


async def test_apartment_with_sufficient_capacity_is_available(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id, max_guests=6)
    await _make_rate_rule(db_session, apartment.id)

    service = _availability_service(db_session)
    check_in = date.today() + timedelta(days=65)
    results = await service.search(check_in, check_in + timedelta(days=3), guests=4)

    assert len(results) == 1
    assert results[0].apartment.id == apartment.id


async def test_inactive_apartment_is_excluded(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    await ApartmentService(
        ApartmentRepository(db_session), OwnerRepository(db_session)
    ).deactivate_apartment(apartment.id)

    service = _availability_service(db_session)
    check_in = date.today() + timedelta(days=70)
    results = await service.search(check_in, check_in + timedelta(days=3), guests=2)

    assert results == []


async def test_apartment_with_no_rate_rule_is_excluded(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    await _make_apartment(db_session, owner.id)

    service = _availability_service(db_session)
    check_in = date.today() + timedelta(days=80)
    results = await service.search(check_in, check_in + timedelta(days=3), guests=2)

    assert results == []


async def test_search_rejects_check_out_not_after_check_in(db_session: AsyncSession) -> None:
    service = _availability_service(db_session)
    check_in = date.today() + timedelta(days=90)

    with pytest.raises(InvalidAvailabilitySearchError):
        await service.search(check_in, check_in, guests=2)

    with pytest.raises(InvalidAvailabilitySearchError):
        await service.search(check_in, check_in - timedelta(days=1), guests=2)
