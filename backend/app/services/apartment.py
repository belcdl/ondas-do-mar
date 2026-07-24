import uuid

from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.apartment import Apartment
from app.repositories.apartment import ApartmentRepository
from app.repositories.owner import OwnerRepository
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.services.owner_guard import ensure_owner_is_active


class ApartmentNotFoundError(NotFoundError):
    """Raised when no apartment exists for the given id."""


class ApartmentService:
    """Business rules for Apartment. Delegates all persistence to ApartmentRepository."""

    def __init__(self, repository: ApartmentRepository, owner_repository: OwnerRepository) -> None:
        self.repository = repository
        self.owner_repository = owner_repository

    async def create_apartment(self, data: ApartmentCreate) -> Apartment:
        await ensure_owner_is_active(self.owner_repository, data.owner_id)

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
        try:
            return await self.repository.create(apartment)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError("Could not create apartment") from exc

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
            await ensure_owner_is_active(self.owner_repository, new_owner_id)

        for field, value in updates.items():
            setattr(apartment, field, value)

        try:
            return await self.repository.update(apartment)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError("Could not update apartment") from exc

    async def deactivate_apartment(self, apartment_id: uuid.UUID) -> Apartment:
        apartment = await self.get_apartment(apartment_id)
        if apartment.is_active:
            apartment.is_active = False
            apartment = await self.repository.update(apartment)
        return apartment
