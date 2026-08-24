import io
import logging
import uuid

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageFilter

from app.core import storage
from app.core.exceptions import BusinessRuleError, NotFoundError, ValidationError
from app.models.apartment_photo import ApartmentPhoto
from app.repositories.apartment_photo import ApartmentPhotoRepository

logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB
_MAX_PHOTOS_PER_APARTMENT = 20

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_MAX_DIMENSION_PX = 2000


class ApartmentPhotoNotFoundError(NotFoundError):
    """Raised when no apartment photo exists for the given id."""


class InvalidPhotoContentTypeError(ValidationError):
    """Raised when an uploaded file isn't one of the allowed image types."""


class PhotoTooLargeError(ValidationError):
    """Raised when an uploaded file exceeds the maximum allowed size."""


class TooManyPhotosError(BusinessRuleError):
    """Raised when an apartment already has the maximum number of photos."""


class ApartmentPhotoService:
    """Business rules for ApartmentPhoto. Delegates persistence to
    ApartmentPhotoRepository and object storage to app.core.storage."""

    def __init__(self, repository: ApartmentPhotoRepository) -> None:
        self.repository = repository

    async def upload_photo(self, apartment_id: uuid.UUID, file: UploadFile) -> ApartmentPhoto:
        if file.content_type not in _ALLOWED_CONTENT_TYPES:
            raise InvalidPhotoContentTypeError(
                "Photo must be one of: image/jpeg, image/png, image/webp"
            )

        file_bytes = await file.read()
        if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
            raise PhotoTooLargeError("Photo must not exceed 8 MB")

        photo_count = await self.repository.count_by_apartment(apartment_id)
        if photo_count >= _MAX_PHOTOS_PER_APARTMENT:
            raise TooManyPhotosError(
                f"An apartment can have at most {_MAX_PHOTOS_PER_APARTMENT} photos"
            )

        upload_bytes = file_bytes
        content_type = file.content_type
        extension = _CONTENT_TYPE_EXTENSIONS[file.content_type]
        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.load()
            if max(image.size) > _MAX_DIMENSION_PX:
                image.thumbnail((_MAX_DIMENSION_PX, _MAX_DIMENSION_PX), Image.LANCZOS)
            image = image.filter(
                ImageFilter.UnsharpMask(radius=1.5, percent=60, threshold=3)
            )
            webp_buffer = io.BytesIO()
            image.save(webp_buffer, format="WEBP", quality=82, method=6)
            upload_bytes = webp_buffer.getvalue()
            content_type = "image/webp"
            extension = "webp"
        except Exception as exc:
            logger.warning(
                "Could not convert apartment %s photo to WebP, uploading original file: %s",
                apartment_id,
                exc,
            )

        key = f"apartments/{apartment_id}/{uuid.uuid4()}.{extension}"
        await run_in_threadpool(storage.upload_photo, upload_bytes, key, content_type)

        photo = ApartmentPhoto(
            apartment_id=apartment_id,
            storage_key=key,
            position=photo_count,
        )
        return await self.repository.create(photo)

    async def list_photos(self, apartment_id: uuid.UUID) -> list[ApartmentPhoto]:
        photos = await self.repository.list_by_apartment(apartment_id)
        return list(photos)

    async def get_photo(self, photo_id: uuid.UUID) -> ApartmentPhoto:
        photo = await self.repository.get_by_id(photo_id)
        if photo is None:
            raise ApartmentPhotoNotFoundError(f"Apartment photo {photo_id} not found")
        return photo

    async def delete_photo(self, photo_id: uuid.UUID) -> None:
        # Delete from R2 first: if that fails, leave the DB record in place
        # rather than end up with a record pointing at nothing. A photo
        # orphaned in the bucket (DB delete failing after a successful R2
        # delete) is the acceptable failure mode here, not the reverse.
        photo = await self.get_photo(photo_id)
        await run_in_threadpool(storage.delete_photo, photo.storage_key)
        await self.repository.delete(photo)
