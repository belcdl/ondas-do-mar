import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.booking import BookingCreate
from app.schemas.owner import OwnerCreate
from app.schemas.rate_rule import RateRuleCreate, RateRuleUpdate
from app.services.apartment import ApartmentService
from app.services.booking import BookingService
from app.services.owner import OwnerService
from app.services.rate_rule import (
    InvalidRateRuleDatesError,
    OverlappingRateRuleError,
    RateRuleInUseError,
    RateRuleNotFoundError,
    RateRuleService,
)


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


def _rate_rule_payload(apartment_id: uuid.UUID, **overrides: object) -> RateRuleCreate:
    payload = {
        "apartment_id": apartment_id,
        "start_date": date.today(),
        "end_date": date.today() + timedelta(days=10),
        "price_per_night": Decimal("90.00"),
        "min_stay": 1,
    }
    payload.update(overrides)
    return RateRuleCreate(**payload)


async def test_rate_rule_lifecycle(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _rate_rule_service(db_session)

    created = await service.create_rate_rule(_rate_rule_payload(apartment.id))
    assert created.apartment_id == apartment.id
    assert created.min_stay == 1

    fetched = await service.get_rate_rule(created.id)
    assert fetched.price_per_night == Decimal("90.00")

    rules = await service.list_rate_rules_by_apartment(apartment.id)
    assert [r.id for r in rules] == [created.id]

    updated = await service.update_rate_rule(
        created.id, RateRuleUpdate(price_per_night=Decimal("120.00"))
    )
    assert updated.price_per_night == Decimal("120.00")

    await service.delete_rate_rule(created.id)
    with pytest.raises(RateRuleNotFoundError):
        await service.get_rate_rule(created.id)


async def test_create_rate_rule_end_before_start_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _rate_rule_service(db_session)

    with pytest.raises(InvalidRateRuleDatesError):
        await service.create_rate_rule(
            _rate_rule_payload(
                apartment.id,
                start_date=date.today() + timedelta(days=10),
                end_date=date.today(),
            )
        )


async def test_create_overlapping_rate_rule_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _rate_rule_service(db_session)

    await service.create_rate_rule(
        _rate_rule_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
    )

    with pytest.raises(OverlappingRateRuleError):
        await service.create_rate_rule(
            _rate_rule_payload(
                apartment.id,
                start_date=date.today() + timedelta(days=15),
                end_date=date.today() + timedelta(days=25),
            )
        )


async def test_adjacent_rate_rules_are_allowed(db_session: AsyncSession) -> None:
    """Inclusive '[]' ranges: end_date of one rule and start_date of the next
    must differ by at least a day, unlike bookings' half-open '[)' adjacency."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _rate_rule_service(db_session)

    await service.create_rate_rule(
        _rate_rule_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
    )
    second = await service.create_rate_rule(
        _rate_rule_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=21),
            end_date=date.today() + timedelta(days=30),
        )
    )
    assert second.start_date == date.today() + timedelta(days=21)


async def test_update_rate_rule_to_overlap_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _rate_rule_service(db_session)

    await service.create_rate_rule(
        _rate_rule_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
    )
    second = await service.create_rate_rule(
        _rate_rule_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=40),
        )
    )

    with pytest.raises(OverlappingRateRuleError):
        await service.update_rate_rule(
            second.id, RateRuleUpdate(start_date=date.today() + timedelta(days=15))
        )


async def test_update_rate_rule_end_before_start_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _rate_rule_service(db_session)

    created = await service.create_rate_rule(_rate_rule_payload(apartment.id))

    with pytest.raises(InvalidRateRuleDatesError):
        await service.update_rate_rule(
            created.id, RateRuleUpdate(end_date=created.start_date - timedelta(days=1))
        )


async def test_delete_rate_rule_not_found(db_session: AsyncSession) -> None:
    service = _rate_rule_service(db_session)
    with pytest.raises(RateRuleNotFoundError):
        await service.delete_rate_rule(uuid.uuid4())


async def test_delete_rate_rule_blocked_by_confirmed_booking(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    rate_rule_service = _rate_rule_service(db_session)
    booking_service = _booking_service(db_session)

    rate_rule = await rate_rule_service.create_rate_rule(_rate_rule_payload(apartment.id))
    booking = await booking_service.create_booking(
        BookingCreate(
            apartment_id=apartment.id,
            guest_full_name="Jane Guest",
            guest_email="jane@example.com",
            guest_count=2,
            check_in_date=rate_rule.start_date,
            check_out_date=rate_rule.start_date + timedelta(days=3),
        )
    )
    await booking_service.confirm_booking(booking.id)

    with pytest.raises(RateRuleInUseError):
        await rate_rule_service.delete_rate_rule(rate_rule.id)


async def test_delete_rate_rule_allowed_when_booking_not_confirmed(
    db_session: AsyncSession,
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    rate_rule_service = _rate_rule_service(db_session)
    booking_service = _booking_service(db_session)

    rate_rule = await rate_rule_service.create_rate_rule(_rate_rule_payload(apartment.id))
    await booking_service.create_booking(
        BookingCreate(
            apartment_id=apartment.id,
            guest_full_name="Jane Guest",
            guest_email="jane@example.com",
            guest_count=2,
            check_in_date=rate_rule.start_date,
            check_out_date=rate_rule.start_date + timedelta(days=3),
        )
    )
    # Never confirmed — stays PENDING, so it must not block deletion.
    await rate_rule_service.delete_rate_rule(rate_rule.id)
    with pytest.raises(RateRuleNotFoundError):
        await rate_rule_service.get_rate_rule(rate_rule.id)
