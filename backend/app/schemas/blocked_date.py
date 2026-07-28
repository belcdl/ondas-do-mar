import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class BlockedDateBase(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = None


class BlockedDateCreate(BlockedDateBase):
    apartment_id: uuid.UUID


class BlockedDateUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = None


class BlockedDateRead(BlockedDateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apartment_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
