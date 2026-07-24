import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OwnerBase(BaseModel):
    full_name: str
    email: str
    phone: str | None = None


class OwnerCreate(OwnerBase):
    pass


class OwnerUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    user_id: uuid.UUID | None = None


class OwnerRead(OwnerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
