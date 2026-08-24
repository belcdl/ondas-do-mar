import uuid
from datetime import timedelta

from icalendar import Calendar, Event

from app.models.booking import BookingStatus
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.booking import BookingRepository

_PRODID = "-//Ondas do Mar//Availability Export//EN"


class IcalExportService:
    """Step 1 of iCal sync: exports our own availability (confirmed bookings
    + manually-blocked dates) as an iCal feed an external platform (e.g.
    Booking.com) can subscribe to. Reading a feed FROM an external platform
    is step 2, not implemented here."""

    def __init__(
        self,
        booking_repository: BookingRepository,
        blocked_date_repository: BlockedDateRepository,
    ) -> None:
        self.booking_repository = booking_repository
        self.blocked_date_repository = blocked_date_repository

    async def build_calendar(self, apartment_id: uuid.UUID) -> Calendar:
        calendar = Calendar()
        calendar.add("prodid", _PRODID)
        calendar.add("version", "2.0")

        bookings = await self.booking_repository.list_all(
            apartment_id=apartment_id, status=BookingStatus.CONFIRMED
        )
        for booking in bookings:
            event = Event()
            event.add("uid", f"booking-{booking.id}@ondasdomar.com")
            # check_out_date is already exclusive (the departure night isn't
            # occupied) — same criterion as services/availability.py, so no
            # adjustment needed for dtend here.
            event.add("dtstart", booking.check_in_date)
            event.add("dtend", booking.check_out_date)
            # Never the guest's name — this feed is public, unauthenticated.
            event.add("summary", "Reserved")
            calendar.add_component(event)

        blocked_dates = await self.blocked_date_repository.list_by_apartment(apartment_id)
        for blocked_date in blocked_dates:
            if blocked_date.ical_source_id is not None:
                # Imported from another platform's feed — re-exporting it
                # would echo it straight back to wherever it came from.
                continue

            event = Event()
            event.add("uid", f"blocked-{blocked_date.id}@ondasdomar.com")
            event.add("dtstart", blocked_date.start_date)
            # BlockedDate.end_date is inclusive (ex_blocked_dates_no_overlap
            # uses a '[]' daterange — that last night is blocked too), but an
            # all-day VEVENT's DTEND is exclusive, so it needs +1 day here.
            event.add("dtend", blocked_date.end_date + timedelta(days=1))
            event.add("summary", "Blocked")
            calendar.add_component(event)

        return calendar
