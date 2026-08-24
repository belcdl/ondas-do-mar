import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict


class IcalSourceBase(BaseModel):
    platform_name: str
    ical_url: AnyHttpUrl


class IcalSourceCreate(IcalSourceBase):
    apartment_id: uuid.UUID


class IcalSourceUpdate(BaseModel):
    platform_name: str | None = None
    ical_url: AnyHttpUrl | None = None


class IcalSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apartment_id: uuid.UUID
    platform_name: str
    ical_url: str
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime
    updated_at: datetime
