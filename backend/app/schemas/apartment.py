import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.apartment import AmenityType


class ApartmentBase(BaseModel):
    owner_id: uuid.UUID
    name: str
    address_line: str
    city: str
    postal_code: str | None = None
    country: str
    description: str | None = None
    bedrooms: int | None = None
    max_guests: int = Field(default=4, gt=0)
    amenities: list[AmenityType] = Field(default_factory=list)
    amenities_other: str | None = None


class ApartmentCreate(ApartmentBase):
    pass


class ApartmentUpdate(BaseModel):
    owner_id: uuid.UUID | None = None
    name: str | None = None
    address_line: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None
    description: str | None = None
    bedrooms: int | None = None
    max_guests: int | None = Field(default=None, gt=0)
    amenities: list[AmenityType] | None = None
    amenities_other: str | None = None
    is_active: bool | None = None


class ApartmentRead(ApartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
