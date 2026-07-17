import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_owner_service
from app.models.owner import Owner
from app.schemas.owner import OwnerCreate, OwnerRead, OwnerUpdate
from app.services.owner import OwnerService

router = APIRouter(prefix="/owners", tags=["owners"])


@router.post("", response_model=OwnerRead, status_code=status.HTTP_201_CREATED)
async def create_owner(
    data: OwnerCreate, service: OwnerService = Depends(get_owner_service)
) -> Owner:
    """Register a new owner. Returns 409 if the email is already registered."""
    return await service.create_owner(data)


@router.get("", response_model=list[OwnerRead])
async def list_owners(
    include_inactive: bool = Query(
        False, description="Include deactivated owners in the results."
    ),
    service: OwnerService = Depends(get_owner_service),
) -> list[Owner]:
    """List owners. Only active owners are returned unless include_inactive=true."""
    return await service.list_owners(include_inactive=include_inactive)


@router.get("/{owner_id}", response_model=OwnerRead)
async def get_owner(
    owner_id: uuid.UUID, service: OwnerService = Depends(get_owner_service)
) -> Owner:
    """Fetch a single owner by id. Returns 404 if no owner exists with that id."""
    return await service.get_owner(owner_id)


@router.patch("/{owner_id}", response_model=OwnerRead)
async def update_owner(
    owner_id: uuid.UUID,
    data: OwnerUpdate,
    service: OwnerService = Depends(get_owner_service),
) -> Owner:
    """Partially update an owner. Only the fields provided in the body are changed."""
    return await service.update_owner(owner_id, data)


@router.post("/{owner_id}/deactivate", response_model=OwnerRead)
async def deactivate_owner(
    owner_id: uuid.UUID, service: OwnerService = Depends(get_owner_service)
) -> Owner:
    """Deactivate an owner (sets is_active=false). Does not delete any data."""
    return await service.deactivate_owner(owner_id)
