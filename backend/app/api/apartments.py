import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    authorize_owner_match,
    get_apartment_photo_service,
    get_apartment_service,
    get_authorized_apartment,
    get_current_active_user,
    get_current_owner_or_none,
)
from app.core.exceptions import PermissionDeniedError
from app.models.apartment import Apartment
from app.models.owner import Owner
from app.models.user import User, UserRole
from app.schemas.apartment import (
    ApartmentCreate,
    ApartmentPublicRead,
    ApartmentRead,
    ApartmentUpdate,
)
from app.schemas.apartment_photo import ApartmentPhotoRead
from app.services.apartment import ApartmentNotFoundError, ApartmentService
from app.services.apartment_photo import ApartmentPhotoService

router = APIRouter(prefix="/apartments", tags=["apartments"])


@router.post("", response_model=ApartmentRead, status_code=status.HTTP_201_CREATED)
async def create_apartment(
    data: ApartmentCreate,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: ApartmentService = Depends(get_apartment_service),
) -> Apartment:
    """Create an apartment. An owner may only create apartments for their own
    owner_id (403 otherwise); an admin may create for any owner. Also 404 if
    the owner doesn't exist, 422 if inactive or dates are invalid."""
    authorize_owner_match(current_user, caller_owner, data.owner_id)
    return await service.create_apartment(data)


@router.get("", response_model=list[ApartmentRead])
async def list_apartments(
    include_inactive: bool = Query(
        False, description="Include deactivated apartments in the results."
    ),
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: ApartmentService = Depends(get_apartment_service),
) -> list[Apartment]:
    """List apartments. An admin sees all; an owner sees only their own."""
    if current_user.role == UserRole.ADMIN:
        return await service.list_apartments(include_inactive=include_inactive)
    if caller_owner is None:
        return []
    return await service.list_apartments_by_owner(
        caller_owner.id, include_inactive=include_inactive
    )


@router.get("/{apartment_id}/public", response_model=ApartmentPublicRead)
async def get_apartment_public(
    apartment_id: uuid.UUID,
    service: ApartmentService = Depends(get_apartment_service),
    photo_service: ApartmentPhotoService = Depends(get_apartment_photo_service),
) -> ApartmentPublicRead:
    """Public apartment listing for guests, no authentication required. 404
    if the apartment doesn't exist or isn't active — same status either way
    so a deactivated listing's existence isn't revealed."""
    apartment = await service.get_apartment(apartment_id)
    if not apartment.is_active:
        raise ApartmentNotFoundError(f"Apartment {apartment_id} not found")

    photos = await photo_service.list_photos(apartment.id)
    return ApartmentPublicRead(
        id=apartment.id,
        name=apartment.name,
        description=apartment.description,
        address_line=apartment.address_line,
        city=apartment.city,
        postal_code=apartment.postal_code,
        country=apartment.country,
        bedrooms=apartment.bedrooms,
        max_guests=apartment.max_guests,
        amenities=apartment.amenities,
        amenities_other=apartment.amenities_other,
        photos=[ApartmentPhotoRead.model_validate(photo).url for photo in photos],
    )


@router.get("/{apartment_id}", response_model=ApartmentRead)
async def get_apartment(apartment: Apartment = Depends(get_authorized_apartment)) -> Apartment:
    """Fetch a single apartment. 404 if it doesn't exist, 403 if it exists but isn't the caller's."""
    return apartment


@router.patch("/{apartment_id}", response_model=ApartmentRead)
async def update_apartment(
    data: ApartmentUpdate,
    current_user: User = Depends(get_current_active_user),
    apartment: Apartment = Depends(get_authorized_apartment),
    service: ApartmentService = Depends(get_apartment_service),
) -> Apartment:
    """Partially update an apartment. Reassigning owner_id to a different
    owner is admin-only — an owner cannot give away or reassign their
    apartments, even to another owner they don't control."""
    if "owner_id" in data.model_fields_set and current_user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Only an admin can reassign an apartment's owner")
    return await service.update_apartment(apartment.id, data)


@router.post("/{apartment_id}/deactivate", response_model=ApartmentRead)
async def deactivate_apartment(
    apartment: Apartment = Depends(get_authorized_apartment),
    service: ApartmentService = Depends(get_apartment_service),
) -> Apartment:
    """Deactivate an apartment (sets is_active=false). Does not delete any data."""
    return await service.deactivate_apartment(apartment.id)
