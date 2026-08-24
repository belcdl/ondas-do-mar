import uuid

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_apartment_service, get_ical_export_service
from app.services.apartment import ApartmentService
from app.services.ical_export import IcalExportService

router = APIRouter(tags=["ical-export"])


@router.get("/apartments/{apartment_id}/calendar.ics")
async def export_apartment_calendar(
    apartment_id: uuid.UUID,
    apartment_service: ApartmentService = Depends(get_apartment_service),
    export_service: IcalExportService = Depends(get_ical_export_service),
) -> Response:
    """Public iCal export of an apartment's confirmed bookings and manually
    blocked dates, for subscribing from an external platform (e.g.
    Booking.com). No authentication — the URL itself is the shared secret,
    same as any other iCal calendar feed. 404 if the apartment doesn't
    exist."""
    await apartment_service.get_apartment(apartment_id)

    calendar = await export_service.build_calendar(apartment_id)
    return Response(
        content=calendar.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="calendar.ics"'},
    )
