from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_authorized_apartment,
    get_authorized_ical_source,
    get_ical_source_service,
)
from app.models.apartment import Apartment
from app.models.ical_source import IcalSource
from app.schemas.ical_source import (
    IcalSourceBase,
    IcalSourceCreate,
    IcalSourceRead,
    IcalSourceUpdate,
)
from app.services.ical_source import IcalSourceService

router = APIRouter(tags=["ical-sources"])


@router.post(
    "/apartments/{apartment_id}/ical-sources",
    response_model=IcalSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_ical_source(
    data: IcalSourceBase,
    apartment: Apartment = Depends(get_authorized_apartment),
    service: IcalSourceService = Depends(get_ical_source_service),
) -> IcalSource:
    """Create an iCal source for an apartment. Same pattern as
    create_blocked_date: the request body has no apartment_id of its own
    (IcalSourceBase, not IcalSourceCreate) — it always comes from the URL,
    which is also what authorization is checked against. 422 if ical_url
    isn't a valid http/https URL."""
    return await service.create_ical_source(
        IcalSourceCreate(apartment_id=apartment.id, **data.model_dump())
    )


@router.get("/apartments/{apartment_id}/ical-sources", response_model=list[IcalSourceRead])
async def list_ical_sources(
    apartment: Apartment = Depends(get_authorized_apartment),
    service: IcalSourceService = Depends(get_ical_source_service),
) -> list[IcalSource]:
    """List iCal sources for an apartment. Same ownership rule as create."""
    return await service.list_ical_sources_by_apartment(apartment.id)


@router.patch("/ical-sources/{ical_source_id}", response_model=IcalSourceRead)
async def update_ical_source(
    data: IcalSourceUpdate,
    ical_source: IcalSource = Depends(get_authorized_ical_source),
    service: IcalSourceService = Depends(get_ical_source_service),
) -> IcalSource:
    """Partially update an iCal source. 404 if it doesn't exist, 403 if it
    exists but isn't the caller's, 422 if the new ical_url isn't a valid
    http/https URL."""
    return await service.update_ical_source(ical_source.id, data)


@router.delete("/ical-sources/{ical_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ical_source(
    ical_source: IcalSource = Depends(get_authorized_ical_source),
    service: IcalSourceService = Depends(get_ical_source_service),
) -> None:
    """Delete an iCal source. Cascades to delete any BlockedDate rows
    imported from it (FK ondelete=CASCADE on blocked_dates.ical_source_id)."""
    await service.delete_ical_source(ical_source.id)
