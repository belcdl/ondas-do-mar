import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_apartment_service
from app.models.apartment import Apartment
from app.schemas.apartment import ApartmentCreate, ApartmentRead, ApartmentUpdate
from app.services.apartment import ApartmentService

router = APIRouter(prefix="/apartments", tags=["apartments"])


@router.post("", response_model=ApartmentRead, status_code=status.HTTP_201_CREATED)
async def create_apartment(
    data: ApartmentCreate, service: ApartmentService = Depends(get_apartment_service)
) -> Apartment:
    """Register a new apartment. Returns 404 if the owner doesn't exist, 422 if inactive."""
    return await service.create_apartment(data)


@router.get("", response_model=list[ApartmentRead])
async def list_apartments(
    include_inactive: bool = Query(
        False, description="Include deactivated apartments in the results."
    ),
    service: ApartmentService = Depends(get_apartment_service),
) -> list[Apartment]:
    """List apartments. Only active apartments are returned unless include_inactive=true."""
    return await service.list_apartments(include_inactive=include_inactive)


@router.get("/{apartment_id}", response_model=ApartmentRead)
async def get_apartment(
    apartment_id: uuid.UUID, service: ApartmentService = Depends(get_apartment_service)
) -> Apartment:
    """Fetch a single apartment by id. Returns 404 if no apartment exists with that id."""
    return await service.get_apartment(apartment_id)


@router.patch("/{apartment_id}", response_model=ApartmentRead)
async def update_apartment(
    apartment_id: uuid.UUID,
    data: ApartmentUpdate,
    service: ApartmentService = Depends(get_apartment_service),
) -> Apartment:
    """Partially update an apartment. Reassigning owner_id requires the new owner to exist and be active."""
    return await service.update_apartment(apartment_id, data)


@router.post("/{apartment_id}/deactivate", response_model=ApartmentRead)
async def deactivate_apartment(
    apartment_id: uuid.UUID, service: ApartmentService = Depends(get_apartment_service)
) -> Apartment:
    """Deactivate an apartment (sets is_active=false). Does not delete any data."""
    return await service.deactivate_apartment(apartment_id)
