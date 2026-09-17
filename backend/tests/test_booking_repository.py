import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.booking import BookingCreate
from app.schemas.owner import OwnerCreate
from app.schemas.rate_rule import RateRuleCreate
from app.services.apartment import ApartmentService
from app.services.booking import BookingService
from app.services.owner import OwnerService
from app.services.rate_rule import RateRuleService

# --- fixtures (mirrors test_payment_service.py's pattern) ---


async def _make_owner(db_session: AsyncSession, **overrides: str | None):
    service = OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": None,
    }
    payload.update(overrides)
    return await service.create_owner(OwnerCreate(**payload))


async def _make_apartment(db_session: AsyncSession, owner_id: uuid.UUID, **overrides: object):
    service = ApartmentService(ApartmentRepository(db_session), OwnerRepository(db_session))
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    return await service.create_apartment(ApartmentCreate(**payload))


async def _make_rate_rule(db_session: AsyncSession, apartment_id: uuid.UUID, **overrides: object):
    service = RateRuleService(RateRuleRepository(db_session), BookingRepository(db_session))
    payload = {
        "apartment_id": apartment_id,
        "start_date": date.today() - timedelta(days=30),
        "end_date": date.today() + timedelta(days=400),
        "price_per_night": Decimal("90.00"),
        "min_stay": 1,
    }
    payload.update(overrides)
    return await service.create_rate_rule(RateRuleCreate(**payload))


def _booking_service(db_session: AsyncSession) -> BookingService:
    return BookingService(
        BookingRepository(db_session),
        ApartmentRepository(db_session),
        OwnerRepository(db_session),
        RateRuleService(RateRuleRepository(db_session), BookingRepository(db_session)),
    )


async def _make_booking(
    db_session: AsyncSession, apartment_id: uuid.UUID, check_in: date, check_out: date, **overrides: object
):
    payload = {
        "apartment_id": apartment_id,
        "guest_full_name": "Jane Guest",
        "guest_email": "jane@example.com",
        "guest_phone": None,
        "guest_count": 2,
        "check_in_date": check_in,
        "check_out_date": check_out,
    }
    payload.update(overrides)
    return await _booking_service(db_session).create_booking(BookingCreate(**payload))


async def test_list_pending_checkin_reminders(db_session: AsyncSession) -> None:
    owner = await _make_owner(db_session)
    booking_repository = BookingRepository(db_session)
    booking_service = _booking_service(db_session)

    today = date.today()
    tomorrow = today + timedelta(days=1)

    # Confirmed, check-in tomorrow, never reminded — included.
    apt_tomorrow = await _make_apartment(db_session, owner.id, name="Apt Tomorrow")
    await _make_rate_rule(db_session, apt_tomorrow.id)
    booking_tomorrow = await _make_booking(
        db_session, apt_tomorrow.id, tomorrow, tomorrow + timedelta(days=2)
    )
    await booking_service.confirm_booking(booking_tomorrow.id)

    # Confirmed, check-in today, never reminded — included (safety net for a
    # missed/failed run yesterday).
    apt_today = await _make_apartment(db_session, owner.id, name="Apt Today")
    await _make_rate_rule(db_session, apt_today.id)
    booking_today = await _make_booking(db_session, apt_today.id, today, today + timedelta(days=2))
    await booking_service.confirm_booking(booking_today.id)

    # Confirmed, check-in tomorrow, already reminded — excluded.
    apt_reminded = await _make_apartment(db_session, owner.id, name="Apt Reminded")
    await _make_rate_rule(db_session, apt_reminded.id)
    booking_reminded = await _make_booking(
        db_session, apt_reminded.id, tomorrow, tomorrow + timedelta(days=2)
    )
    await booking_service.confirm_booking(booking_reminded.id)
    booking_reminded.checkin_reminder_sent_at = datetime.now(timezone.utc)
    await booking_repository.update(booking_reminded)

    # Still PENDING (unpaid), check-in tomorrow — excluded.
    apt_pending = await _make_apartment(db_session, owner.id, name="Apt Pending")
    await _make_rate_rule(db_session, apt_pending.id)
    await _make_booking(db_session, apt_pending.id, tomorrow, tomorrow + timedelta(days=2))

    # Confirmed, check-in far in the future — excluded.
    apt_far = await _make_apartment(db_session, owner.id, name="Apt Far")
    await _make_rate_rule(db_session, apt_far.id)
    booking_far = await _make_booking(
        db_session, apt_far.id, today + timedelta(days=10), today + timedelta(days=12)
    )
    await booking_service.confirm_booking(booking_far.id)

    result = await booking_repository.list_pending_checkin_reminders(today, tomorrow)
    result_ids = {booking.id for booking in result}

    assert result_ids == {booking_tomorrow.id, booking_today.id}
