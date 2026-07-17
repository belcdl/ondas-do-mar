import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.owner import OwnerRepository
from app.schemas.owner import OwnerCreate, OwnerUpdate
from app.services.owner import (
    OwnerEmailAlreadyExistsError,
    OwnerNotFoundError,
    OwnerService,
)


async def test_owner_service_lifecycle(db_session: AsyncSession) -> None:
    service = OwnerService(OwnerRepository(db_session))
    email = f"test-{uuid.uuid4()}@example.com"

    created = await service.create_owner(
        OwnerCreate(full_name="Test Owner", email=email, phone=None)
    )
    assert created.is_active is True

    with pytest.raises(OwnerEmailAlreadyExistsError):
        await service.create_owner(OwnerCreate(full_name="Duplicate", email=email, phone=None))

    fetched = await service.get_owner(created.id)
    assert fetched.email == email

    owners = await service.list_owners()
    assert any(o.id == created.id for o in owners)

    updated = await service.update_owner(created.id, OwnerUpdate(phone="+34123456789"))
    assert updated.phone == "+34123456789"

    deactivated = await service.deactivate_owner(created.id)
    assert deactivated.is_active is False

    active_owners = await service.list_owners()
    assert all(o.id != created.id for o in active_owners)

    with pytest.raises(OwnerNotFoundError):
        await service.get_owner(uuid.uuid4())
