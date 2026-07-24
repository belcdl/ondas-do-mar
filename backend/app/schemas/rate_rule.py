import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RateRuleBase(BaseModel):
    start_date: date
    end_date: date
    price_per_night: Decimal = Field(gt=0)
    min_stay: int = Field(default=1, gt=0)


class RateRuleCreate(RateRuleBase):
    apartment_id: uuid.UUID


class RateRuleUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    price_per_night: Decimal | None = Field(default=None, gt=0)
    min_stay: int | None = Field(default=None, gt=0)


class RateRuleRead(RateRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apartment_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
