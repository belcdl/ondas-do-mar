import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import scheduler
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

# --- fixtures (mirrors test_booking_repository.py's pattern) ---


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


async def _make_confirmed_booking(db_session: AsyncSession, owner_id: uuid.UUID, name: str):
    """A CONFIRMED booking checking in tomorrow, on its own apartment (so
    the confirmed-overlap exclusion constraint never gets in the way of
    multiple bookings in the same test)."""
    apartment = await _make_apartment(db_session, owner_id, name=name)
    await _make_rate_rule(db_session, apartment.id)
    tomorrow = date.today() + timedelta(days=1)
    booking_service = _booking_service(db_session)
    booking = await booking_service.create_booking(
        BookingCreate(
            apartment_id=apartment.id,
            guest_full_name="Jane Guest",
            guest_email="jane@example.com",
            guest_phone=None,
            guest_count=2,
            check_in_date=tomorrow,
            check_out_date=tomorrow + timedelta(days=2),
        )
    )
    return await booking_service.confirm_booking(booking.id)


class _FakeSessionFactory:
    """Redirects app.core.scheduler's own `async with async_session_factory()`
    to the test's transactional db_session, so the job's writes are visible
    to (and rolled back with) the rest of the test — same reasoning as
    tests/conftest.py's db_session fixture itself."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> "_FakeSessionFactory":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


async def test_checkin_reminders_job_sends_and_marks_sent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduler, "async_session_factory", _FakeSessionFactory(db_session))

    owner = await _make_owner(db_session)
    booking = await _make_confirmed_booking(db_session, owner.id, "Apt")
    assert booking.checkin_reminder_sent_at is None

    sent_for = []

    class _FakeEmailService:
        async def send_checkin_reminder(self, booking, apartment, owner) -> None:
            sent_for.append(booking.id)

    monkeypatch.setattr(scheduler, "EmailService", _FakeEmailService)

    await scheduler._send_checkin_reminders()

    assert sent_for == [booking.id]
    assert booking.checkin_reminder_sent_at is not None


async def test_checkin_reminders_job_isolates_failures_per_booking(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One booking's send failing must not stop the other's in the same
    tick, and only the one that failed should be left unmarked (so it's
    retried tomorrow — see list_pending_checkin_reminders' 2-day window)."""
    monkeypatch.setattr(scheduler, "async_session_factory", _FakeSessionFactory(db_session))

    owner = await _make_owner(db_session)
    failing_booking = await _make_confirmed_booking(db_session, owner.id, "Apt Failing")
    ok_booking = await _make_confirmed_booking(db_session, owner.id, "Apt Ok")

    sent_for = []

    class _FakeEmailService:
        async def send_checkin_reminder(self, booking, apartment, owner) -> None:
            if booking.id == failing_booking.id:
                raise RuntimeError("smtp connection refused")
            sent_for.append(booking.id)

    monkeypatch.setattr(scheduler, "EmailService", _FakeEmailService)

    await scheduler._send_checkin_reminders()  # must not raise

    assert sent_for == [ok_booking.id]
    assert failing_booking.checkin_reminder_sent_at is None
    assert ok_booking.checkin_reminder_sent_at is not None
