import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.apartment import ApartmentRepository
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.blocked_date import BlockedDateCreate, BlockedDateUpdate
from app.schemas.owner import OwnerCreate
from app.services.apartment import ApartmentService
from app.services.blocked_date import (
    BlockedDateNotFoundError,
    BlockedDateService,
    InvalidBlockedDateDatesError,
    OverlappingBlockedDateError,
)
from app.services.owner import OwnerService


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


def _blocked_date_service(db_session: AsyncSession) -> BlockedDateService:
    return BlockedDateService(BlockedDateRepository(db_session))


def _blocked_date_payload(apartment_id: uuid.UUID, **overrides: object) -> BlockedDateCreate:
    payload = {
        "apartment_id": apartment_id,
        "start_date": date.today() + timedelta(days=10),
        "end_date": date.today() + timedelta(days=20),
        "reason": "Owner maintenance",
    }
    payload.update(overrides)
    return BlockedDateCreate(**payload)


async def test_blocked_date_lifecycle(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _blocked_date_service(db_session)

    created = await service.create_blocked_date(_blocked_date_payload(apartment.id))
    assert created.apartment_id == apartment.id
    assert created.reason == "Owner maintenance"

    fetched = await service.get_blocked_date(created.id)
    assert fetched.id == created.id

    blocked_dates = await service.list_blocked_dates_by_apartment(apartment.id)
    assert [b.id for b in blocked_dates] == [created.id]

    updated = await service.update_blocked_date(
        created.id, BlockedDateUpdate(reason="Renovation")
    )
    assert updated.reason == "Renovation"

    await service.delete_blocked_date(created.id)
    with pytest.raises(BlockedDateNotFoundError):
        await service.get_blocked_date(created.id)


async def test_create_blocked_date_end_before_start_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _blocked_date_service(db_session)

    with pytest.raises(InvalidBlockedDateDatesError):
        await service.create_blocked_date(
            _blocked_date_payload(
                apartment.id,
                start_date=date.today() + timedelta(days=10),
                end_date=date.today(),
            )
        )


async def test_create_overlapping_blocked_date_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _blocked_date_service(db_session)

    await service.create_blocked_date(
        _blocked_date_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
    )

    with pytest.raises(OverlappingBlockedDateError):
        await service.create_blocked_date(
            _blocked_date_payload(
                apartment.id,
                start_date=date.today() + timedelta(days=15),
                end_date=date.today() + timedelta(days=25),
            )
        )


async def test_adjacent_blocked_dates_are_allowed(db_session: AsyncSession) -> None:
    """Inclusive '[]' ranges: end_date of one block and start_date of the
    next must differ by at least a day, same as rate rules."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _blocked_date_service(db_session)

    await service.create_blocked_date(
        _blocked_date_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
    )
    second = await service.create_blocked_date(
        _blocked_date_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=21),
            end_date=date.today() + timedelta(days=30),
        )
    )
    assert second.start_date == date.today() + timedelta(days=21)


async def test_update_blocked_date_to_overlap_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _blocked_date_service(db_session)

    await service.create_blocked_date(
        _blocked_date_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
        )
    )
    second = await service.create_blocked_date(
        _blocked_date_payload(
            apartment.id,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=40),
        )
    )

    with pytest.raises(OverlappingBlockedDateError):
        await service.update_blocked_date(
            second.id, BlockedDateUpdate(start_date=date.today() + timedelta(days=15))
        )


async def test_update_blocked_date_end_before_start_rejected(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    service = _blocked_date_service(db_session)

    created = await service.create_blocked_date(_blocked_date_payload(apartment.id))

    with pytest.raises(InvalidBlockedDateDatesError):
        await service.update_blocked_date(
            created.id, BlockedDateUpdate(end_date=created.start_date - timedelta(days=1))
        )


async def test_get_blocked_date_not_found(db_session: AsyncSession) -> None:
    service = _blocked_date_service(db_session)
    with pytest.raises(BlockedDateNotFoundError):
        await service.get_blocked_date(uuid.uuid4())


async def test_delete_blocked_date_not_found(db_session: AsyncSession) -> None:
    service = _blocked_date_service(db_session)
    with pytest.raises(BlockedDateNotFoundError):
        await service.delete_blocked_date(uuid.uuid4())


async def test_update_blocked_date_not_found(db_session: AsyncSession) -> None:
    service = _blocked_date_service(db_session)
    with pytest.raises(BlockedDateNotFoundError):
        await service.update_blocked_date(uuid.uuid4(), BlockedDateUpdate(reason="Nope"))
