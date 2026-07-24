import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.apartment import ApartmentRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.schemas.owner import OwnerCreate
from app.services.apartment import ApartmentNotFoundError, ApartmentService
from app.services.owner import OwnerNotFoundError, OwnerService
from app.services.owner_guard import InactiveOwnerError


def _owner_service(db_session: AsyncSession) -> OwnerService:
    return OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )


async def _make_owner(db_session: AsyncSession, **overrides: str | None) -> object:
    service = _owner_service(db_session)
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": None,
    }
    payload.update(overrides)
    return await service.create_owner(OwnerCreate(**payload))


def _apartment_service(db_session: AsyncSession) -> ApartmentService:
    return ApartmentService(ApartmentRepository(db_session), OwnerRepository(db_session))


async def test_apartment_lifecycle(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    service = _apartment_service(db_session)

    created = await service.create_apartment(
        ApartmentCreate(
            owner_id=owner.id,
            name="Casa Azul",
            address_line="Rua da Praia 12",
            city="Porto",
            postal_code="4000-000",
            country="Portugal",
        )
    )
    assert created.is_active is True
    assert created.owner_id == owner.id

    fetched = await service.get_apartment(created.id)
    assert fetched.name == "Casa Azul"

    apartments = await service.list_apartments()
    assert any(a.id == created.id for a in apartments)

    updated = await service.update_apartment(created.id, ApartmentUpdate(bedrooms=2))
    assert updated.bedrooms == 2

    deactivated = await service.deactivate_apartment(created.id)
    assert deactivated.is_active is False

    active_apartments = await service.list_apartments()
    assert all(a.id != created.id for a in active_apartments)

    with pytest.raises(ApartmentNotFoundError):
        await service.get_apartment(uuid.uuid4())


async def test_create_apartment_with_nonexistent_owner(db_session: AsyncSession) -> None:
    service = _apartment_service(db_session)
    with pytest.raises(OwnerNotFoundError):
        await service.create_apartment(
            ApartmentCreate(
                owner_id=uuid.uuid4(),
                name="Ghost Apartment",
                address_line="Nowhere 1",
                city="Nowhere",
                country="Nowhere",
            )
        )


async def test_create_apartment_with_inactive_owner(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    owner_service = _owner_service(db_session)
    await owner_service.deactivate_owner(owner.id)

    service = _apartment_service(db_session)
    with pytest.raises(InactiveOwnerError):
        await service.create_apartment(
            ApartmentCreate(
                owner_id=owner.id,
                name="Casa Azul",
                address_line="Rua da Praia 12",
                city="Porto",
                country="Portugal",
            )
        )


async def test_update_apartment_owner_reassignment(db_session: AsyncSession) -> None:
    owner_a = await _make_owner(db_session)
    owner_b = await _make_owner(db_session)
    service = _apartment_service(db_session)

    apartment = await service.create_apartment(
        ApartmentCreate(
            owner_id=owner_a.id,
            name="Casa Azul",
            address_line="Rua da Praia 12",
            city="Porto",
            country="Portugal",
        )
    )

    updated = await service.update_apartment(apartment.id, ApartmentUpdate(owner_id=owner_b.id))
    assert updated.owner_id == owner_b.id


async def test_update_apartment_reassign_to_inactive_owner(db_session: AsyncSession) -> None:
    owner_a = await _make_owner(db_session)
    owner_b = await _make_owner(db_session)
    owner_service = _owner_service(db_session)
    await owner_service.deactivate_owner(owner_b.id)

    service = _apartment_service(db_session)
    apartment = await service.create_apartment(
        ApartmentCreate(
            owner_id=owner_a.id,
            name="Casa Azul",
            address_line="Rua da Praia 12",
            city="Porto",
            country="Portugal",
        )
    )

    with pytest.raises(InactiveOwnerError):
        await service.update_apartment(apartment.id, ApartmentUpdate(owner_id=owner_b.id))
