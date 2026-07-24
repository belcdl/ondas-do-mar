import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.apartment import Apartment
from app.models.owner import Owner
from app.repositories.apartment import ApartmentRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.owner import OwnerCreate
from app.services.apartment import ApartmentService
from app.services.owner import OwnerService


async def test_owner_can_have_multiple_apartments(db_session: AsyncSession) -> None:
    owner_service = OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )
    apartment_service = ApartmentService(
        ApartmentRepository(db_session), OwnerRepository(db_session)
    )

    owner = await owner_service.create_owner(
        OwnerCreate(full_name="Multi Owner", email=f"multi-{uuid.uuid4()}@example.com", phone=None)
    )

    apt1 = await apartment_service.create_apartment(
        ApartmentCreate(
            owner_id=owner.id, name="Apt 1", address_line="Street 1", city="Lisboa", country="Portugal"
        )
    )
    apt2 = await apartment_service.create_apartment(
        ApartmentCreate(
            owner_id=owner.id, name="Apt 2", address_line="Street 2", city="Lisboa", country="Portugal"
        )
    )

    owned = await apartment_service.list_apartments_by_owner(owner.id)
    assert {a.id for a in owned} == {apt1.id, apt2.id}


async def test_owner_with_apartments_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    """Proves the ON DELETE RESTRICT constraint holds at the database level,
    independent of the fact that the app never exposes an Owner delete operation."""
    owner_repo = OwnerRepository(db_session)
    apartment_repo = ApartmentRepository(db_session)

    owner = await owner_repo.create(
        Owner(full_name="Restrict Owner", email=f"restrict-{uuid.uuid4()}@example.com")
    )
    await apartment_repo.create(
        Apartment(
            owner_id=owner.id, name="Apt", address_line="Street", city="Lisboa", country="Portugal"
        )
    )

    await db_session.delete(owner)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
