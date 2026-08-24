import uuid
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from icalendar import Calendar
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocked_date import BlockedDate
from app.models.ical_source import IcalSource
from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.rate_rule import RateRuleRepository
from app.schemas.booking import BookingCreate
from app.schemas.rate_rule import RateRuleCreate
from app.services.booking import BookingService
from app.services.rate_rule import RateRuleService


async def _create_owner(client: AsyncClient, headers: dict[str, str], **overrides: str) -> dict:
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": "+34600000000",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/owners", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_apartment(
    client: AsyncClient, headers: dict[str, str], owner_id: str, **overrides: str
) -> dict:
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/apartments", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


def _booking_service(db_session: AsyncSession) -> BookingService:
    return BookingService(
        BookingRepository(db_session),
        ApartmentRepository(db_session),
        OwnerRepository(db_session),
        RateRuleService(RateRuleRepository(db_session), BookingRepository(db_session)),
    )


async def _make_confirmed_booking(
    db_session: AsyncSession, apartment_id: uuid.UUID, check_in: date, check_out: date
):
    service = _booking_service(db_session)
    await service.rate_rule_service.create_rate_rule(
        RateRuleCreate(
            apartment_id=apartment_id,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=400),
            price_per_night=Decimal("90.00"),
            min_stay=1,
        )
    )

    booking = await service.create_booking(
        BookingCreate(
            apartment_id=apartment_id,
            guest_full_name="Jane Guest",
            guest_email="jane@example.com",
            guest_phone=None,
            guest_count=2,
            check_in_date=check_in,
            check_out_date=check_out,
        )
    )
    return await service.confirm_booking(booking.id)


async def test_export_calendar_apartment_not_found(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/api/v1/apartments/{uuid.uuid4()}/calendar.ics")
    assert response.status_code == 404


async def test_export_calendar_includes_confirmed_booking_and_manual_block_excludes_imported(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    apartment_id = uuid.UUID(apartment["id"])

    booking = await _make_confirmed_booking(
        db_session,
        apartment_id,
        check_in=date(2026, 10, 1),
        check_out=date(2026, 10, 5),
    )

    # Manual blocked date, created through the CRUD endpoint (no
    # ical_source_id) — must be exported, with end_date exclusive-adjusted.
    manual_response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/blocked-dates",
        json={
            "start_date": "2026-09-01",
            "end_date": "2026-09-03",
            "reason": "Owner maintenance",
        },
        headers=admin_headers,
    )
    assert manual_response.status_code == 201
    manual_blocked = manual_response.json()

    # Imported blocked date (ical_source_id set) — must NOT be exported, to
    # avoid echoing it back to the platform it came from. No CRUD endpoint
    # sets ical_source_id, so it's created directly at the ORM level, same
    # as the cascade-delete test in test_ical_source_api.py.
    ical_source = IcalSource(
        apartment_id=apartment_id,
        platform_name="Airbnb",
        ical_url="https://www.airbnb.com/calendar/ical/12345.ics",
    )
    db_session.add(ical_source)
    await db_session.flush()
    imported_blocked = BlockedDate(
        apartment_id=apartment_id,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        ical_source_id=ical_source.id,
        external_uid="event-abc@airbnb.com",
    )
    db_session.add(imported_blocked)
    await db_session.commit()

    response = await client.get(f"/api/v1/apartments/{apartment['id']}/calendar.ics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="calendar.ics"'

    assert "Jane" not in response.text  # guest name must never appear on this public feed

    calendar = Calendar.from_ical(response.content)
    events = list(calendar.walk("VEVENT"))
    assert len(events) == 2

    events_by_uid = {str(event["UID"]): event for event in events}

    booking_uid = f"booking-{booking.id}@ondasdomar.com"
    assert booking_uid in events_by_uid
    booking_event = events_by_uid[booking_uid]
    assert booking_event["DTSTART"].dt == date(2026, 10, 1)
    assert booking_event["DTEND"].dt == date(2026, 10, 5)  # check_out_date, unchanged
    assert str(booking_event["SUMMARY"]) == "Reserved"

    manual_uid = f"blocked-{manual_blocked['id']}@ondasdomar.com"
    assert manual_uid in events_by_uid
    manual_event = events_by_uid[manual_uid]
    assert manual_event["DTSTART"].dt == date(2026, 9, 1)
    # end_date=2026-09-03 is inclusive -> dtend must be end_date + 1 day
    assert manual_event["DTEND"].dt == date(2026, 9, 4)

    imported_uid = f"blocked-{imported_blocked.id}@ondasdomar.com"
    assert imported_uid not in events_by_uid
