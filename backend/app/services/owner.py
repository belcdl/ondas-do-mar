import uuid

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.schemas.owner import OwnerCreate, OwnerUpdate


class OwnerNotFoundError(NotFoundError):
    """Raised when no owner exists for the given id."""


class OwnerEmailAlreadyExistsError(ConflictError):
    """Raised when an email is already registered to a different owner."""


class OwnerService:
    """Business rules for Owner. Delegates all persistence to OwnerRepository."""

    def __init__(self, repository: OwnerRepository) -> None:
        self.repository = repository

    async def create_owner(self, data: OwnerCreate) -> Owner:
        if await self.repository.get_by_email(data.email) is not None:
            raise OwnerEmailAlreadyExistsError(f"Owner with email {data.email} already exists")

        owner = Owner(full_name=data.full_name, email=data.email, phone=data.phone)
        try:
            return await self.repository.create(owner)
        except IntegrityError as exc:
            raise OwnerEmailAlreadyExistsError(
                f"Owner with email {data.email} already exists"
            ) from exc

    async def get_owner(self, owner_id: uuid.UUID) -> Owner:
        owner = await self.repository.get_by_id(owner_id)
        if owner is None:
            raise OwnerNotFoundError(f"Owner {owner_id} not found")
        return owner

    async def list_owners(self, *, include_inactive: bool = False) -> list[Owner]:
        owners = await self.repository.list_all(include_inactive=include_inactive)
        return list(owners)

    async def update_owner(self, owner_id: uuid.UUID, data: OwnerUpdate) -> Owner:
        owner = await self.get_owner(owner_id)

        updates = data.model_dump(exclude_unset=True)
        new_email = updates.get("email")
        if new_email is not None and new_email != owner.email:
            if await self.repository.get_by_email(new_email) is not None:
                raise OwnerEmailAlreadyExistsError(f"Owner with email {new_email} already exists")

        for field, value in updates.items():
            setattr(owner, field, value)

        try:
            return await self.repository.update(owner)
        except IntegrityError as exc:
            raise OwnerEmailAlreadyExistsError(
                f"Owner with email {owner.email} already exists"
            ) from exc

    async def deactivate_owner(self, owner_id: uuid.UUID) -> Owner:
        owner = await self.get_owner(owner_id)
        if owner.is_active:
            owner.is_active = False
            owner = await self.repository.update(owner)
        return owner
