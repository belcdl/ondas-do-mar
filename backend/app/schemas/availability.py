import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class NightPriceRead(BaseModel):
    date: date
    price: Decimal

    model_config = ConfigDict(
        json_schema_extra={"example": {"date": "2027-08-10", "price": "120.00"}}
    )


class ApartmentAvailabilityRead(BaseModel):
    apartment_id: uuid.UUID
    name: str
    guests: int
    nights: int
    currency: str
    price_total: Decimal
    price_breakdown: list[NightPriceRead]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "apartment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "name": "Casa Azul",
                "guests": 4,
                "nights": 5,
                "currency": "EUR",
                "price_total": "780.00",
                "price_breakdown": [
                    {"date": "2027-08-10", "price": "120.00"},
                    {"date": "2027-08-11", "price": "120.00"},
                    {"date": "2027-08-12", "price": "120.00"},
                    {"date": "2027-08-13", "price": "210.00"},
                    {"date": "2027-08-14", "price": "210.00"},
                ],
            }
        }
    )
