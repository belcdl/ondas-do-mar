from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_authorized_apartment,
    get_authorized_blocked_date,
    get_blocked_date_service,
)
from app.models.apartment import Apartment
from app.models.blocked_date import BlockedDate
from app.schemas.blocked_date import (
    BlockedDateBase,
    BlockedDateCreate,
    BlockedDateRead,
    BlockedDateUpdate,
)
from app.services.blocked_date import BlockedDateService

router = APIRouter(tags=["blocked-dates"])


@router.post(
    "/apartments/{apartment_id}/blocked-dates",
    response_model=BlockedDateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_blocked_date(
    data: BlockedDateBase,
    apartment: Apartment = Depends(get_authorized_apartment),
    service: BlockedDateService = Depends(get_blocked_date_service),
) -> BlockedDate:
    """Create a blocked date for an apartment. The request body has no
    apartment_id of its own (BlockedDateBase, not BlockedDateCreate) — it
    always comes from the URL, which is also what authorization is checked
    against, so a caller can never authorize against one apartment and
    create the block under another. 409 if the date range overlaps an
    existing blocked date for this apartment, 422 if end_date is before
    start_date."""
    return await service.create_blocked_date(
        BlockedDateCreate(apartment_id=apartment.id, **data.model_dump())
    )


@router.get("/apartments/{apartment_id}/blocked-dates", response_model=list[BlockedDateRead])
async def list_blocked_dates(
    apartment: Apartment = Depends(get_authorized_apartment),
    service: BlockedDateService = Depends(get_blocked_date_service),
) -> list[BlockedDate]:
    """List blocked dates for an apartment. Same ownership rule as create."""
    return await service.list_blocked_dates_by_apartment(apartment.id)


@router.patch("/blocked-dates/{blocked_date_id}", response_model=BlockedDateRead)
async def update_blocked_date(
    data: BlockedDateUpdate,
    blocked_date: BlockedDate = Depends(get_authorized_blocked_date),
    service: BlockedDateService = Depends(get_blocked_date_service),
) -> BlockedDate:
    """Partially update a blocked date. 404 if it doesn't exist, 403 if it
    exists but isn't the caller's, 409 if the new range overlaps another
    blocked date for the same apartment."""
    return await service.update_blocked_date(blocked_date.id, data)


@router.delete("/blocked-dates/{blocked_date_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blocked_date(
    blocked_date: BlockedDate = Depends(get_authorized_blocked_date),
    service: BlockedDateService = Depends(get_blocked_date_service),
) -> None:
    """Hard-delete a blocked date — unlike a rate rule, it protects no
    existing booking, so it can always be removed freely."""
    await service.delete_blocked_date(blocked_date.id)
