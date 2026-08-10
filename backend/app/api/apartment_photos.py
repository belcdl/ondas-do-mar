from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import (
    get_apartment_photo_service,
    get_authorized_apartment,
    get_authorized_apartment_photo,
)
from app.models.apartment import Apartment
from app.models.apartment_photo import ApartmentPhoto
from app.schemas.apartment_photo import ApartmentPhotoRead
from app.services.apartment_photo import ApartmentPhotoService

router = APIRouter(tags=["apartment-photos"])


@router.post(
    "/apartments/{apartment_id}/photos",
    response_model=ApartmentPhotoRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_apartment_photo(
    file: UploadFile = File(...),
    apartment: Apartment = Depends(get_authorized_apartment),
    service: ApartmentPhotoService = Depends(get_apartment_photo_service),
) -> ApartmentPhoto:
    """Upload a photo for an apartment. 422 if the content type isn't one of
    image/jpeg, image/png, image/webp, if the file exceeds 8 MB, or if the
    apartment already has 20 photos."""
    return await service.upload_photo(apartment.id, file)


@router.get("/apartments/{apartment_id}/photos", response_model=list[ApartmentPhotoRead])
async def list_apartment_photos(
    apartment: Apartment = Depends(get_authorized_apartment),
    service: ApartmentPhotoService = Depends(get_apartment_photo_service),
) -> list[ApartmentPhoto]:
    """List an apartment's photos, ordered by position."""
    return await service.list_photos(apartment.id)


@router.delete(
    "/apartments/{apartment_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_apartment_photo(
    photo: ApartmentPhoto = Depends(get_authorized_apartment_photo),
    service: ApartmentPhotoService = Depends(get_apartment_photo_service),
) -> None:
    """Delete an apartment photo. Removes it from R2 first, then the DB
    record — see ApartmentPhotoService.delete_photo for why."""
    await service.delete_photo(photo.id)
