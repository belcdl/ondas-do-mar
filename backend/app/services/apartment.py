import uuid

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.apartment import Apartment
from app.repositories.apartment import ApartmentRepository
from app.repositories.owner import OwnerRepository
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.services.owner import OwnerNotFoundError


class ApartmentNotFoundError(NotFoundError):
    """Raised when no apartment exists for the given id."""


class InactiveOwnerError(BusinessRuleError):
    """Raised when an apartment is being assigned to an owner that is not active."""


class ApartmentService:
    """Business rules for Apartment. Delegates all persistence to ApartmentRepository."""

    def __init__(self, repository: ApartmentRepository, owner_repository: OwnerRepository) -> None:
        self.repository = repository
        self.owner_repository = owner_repository

    async def _ensure_owner_is_assignable(self, owner_id: uuid.UUID) -> None:
        owner = await self.owner_repository.get_by_id(owner_id)
        if owner is None:
            raise OwnerNotFoundError(f"Owner {owner_id} not found")
        if not owner.is_active:
            raise InactiveOwnerError(f"Owner {owner_id} is not active")

    async def create_apartment(self, data: ApartmentCreate) -> Apartment:
        await self._ensure_owner_is_assignable(data.owner_id)

        apartment = Apartment(
            owner_id=data.owner_id,
            name=data.name,
            address_line=data.address_line,
            city=data.city,
            postal_code=data.postal_code,
            country=data.country,
            description=data.description,
            bedrooms=data.bedrooms,
        )
        return await self.repository.create(apartment)

    async def get_apartment(self, apartment_id: uuid.UUID) -> Apartment:
        apartment = await self.repository.get_by_id(apartment_id)
        if apartment is None:
            raise ApartmentNotFoundError(f"Apartment {apartment_id} not found")
        return apartment

    async def list_apartments(self, *, include_inactive: bool = False) -> list[Apartment]:
        apartments = await self.repository.list_all(include_inactive=include_inactive)
        return list(apartments)

    async def list_apartments_by_owner(
        self, owner_id: uuid.UUID, *, include_inactive: bool = False
    ) -> list[Apartment]:
        apartments = await self.repository.list_by_owner(owner_id, include_inactive=include_inactive)
        return list(apartments)

    async def update_apartment(self, apartment_id: uuid.UUID, data: ApartmentUpdate) -> Apartment:
        apartment = await self.get_apartment(apartment_id)

        updates = data.model_dump(exclude_unset=True)
        new_owner_id = updates.get("owner_id")
        if new_owner_id is not None and new_owner_id != apartment.owner_id:
            await self._ensure_owner_is_assignable(new_owner_id)

        for field, value in updates.items():
            setattr(apartment, field, value)

        return await self.repository.update(apartment)

    async def deactivate_apartment(self, apartment_id: uuid.UUID) -> Apartment:
        apartment = await self.get_apartment(apartment_id)
        if apartment.is_active:
            apartment.is_active = False
            apartment = await self.repository.update(apartment)
        return apartment
