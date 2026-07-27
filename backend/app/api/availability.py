from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_availability_service
from app.schemas.availability import ApartmentAvailabilityRead, NightPriceRead
from app.services.availability import AvailabilityService

router = APIRouter(prefix="/availability", tags=["availability"])

_RESPONSE_EXAMPLE = {
    "application/json": {
        "example": [
            {
                "apartment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "name": "Casa Azul",
                "guests": 4,
                "nights": 5,
                "currency": "EUR",
                "price_total": "780.00",
                "price_breakdown": [
                    {"date": "2027-08-10", "price": "120.00"},
                    {"date": "2027-08-11", "price": "120.00"},
                ],
            }
        ]
    }
}


@router.get(
    "/search",
    response_model=list[ApartmentAvailabilityRead],
    responses={200: {"content": _RESPONSE_EXAMPLE}},
)
async def search_availability(
    check_in: date = Query(..., description="Check-in date (first stayed night)."),
    check_out: date = Query(..., description="Check-out date (must be after check_in)."),
    guests: int = Query(..., gt=0, description="Number of guests the apartment must fit."),
    service: AvailabilityService = Depends(get_availability_service),
) -> list[ApartmentAvailabilityRead]:
    """Search apartments available for the given date range and party size.

    Public — no account is required to search, same as booking creation.
    An apartment is included only if it's active, fits `guests`, has no
    confirmed booking or blocked date overlapping the stay, and every night
    is covered by a rate rule that also satisfies its own minimum stay.
    Returns an empty list (200 OK) when nothing matches — never an error.
    422 if `check_out` is not after `check_in`.
    """
    results = await service.search(check_in, check_out, guests)
    return [
        ApartmentAvailabilityRead(
            apartment_id=result.apartment.id,
            name=result.apartment.name,
            guests=guests,
            nights=result.nights,
            currency=result.currency,
            price_total=result.price_total,
            price_breakdown=[
                NightPriceRead(date=night.night, price=night.price)
                for night in result.price_breakdown
            ],
        )
        for result in results
    ]
