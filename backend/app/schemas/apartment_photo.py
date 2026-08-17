import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import get_settings


class ApartmentPhotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apartment_id: uuid.UUID
    position: int
    created_at: datetime

    # Loaded from the ORM object to derive `url` below, but not a field of
    # its own in the response — storage_key + settings.media_public_base_url
    # is the single source of truth for the object's location, so the full
    # URL is derived here rather than duplicated on the wire.
    storage_key: str = Field(exclude=True, repr=False)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"{get_settings().media_public_base_url}/{self.storage_key}"
