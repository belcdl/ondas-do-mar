import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.repositories.apartment import ApartmentRepository
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.booking import BookingRepository
from app.repositories.ical_source import IcalSourceRepository
from app.repositories.owner import OwnerRepository
from app.services.email import EmailService
from app.services.ical_sync import sync_source

logger = logging.getLogger(__name__)

settings = get_settings()

scheduler = AsyncIOScheduler()

_ICAL_SYNC_JOB_ID = "ical_sync"
_CHECKIN_REMINDERS_JOB_ID = "checkin_reminders"


async def _sync_all_sources() -> None:
    """One tick of the scheduled job: reconciles every IcalSource in the
    database against its feed. Runs outside any request, so it opens its own
    session rather than depending on FastAPI's per-request get_db."""
    async with async_session_factory() as session:
        ical_source_repository = IcalSourceRepository(session)
        blocked_date_repository = BlockedDateRepository(session)
        for ical_source in await ical_source_repository.list_all():
            try:
                await sync_source(ical_source, blocked_date_repository)
            except Exception:
                # sync_source already handles fetch/parse/conflict failures
                # internally without raising — this is a last-resort net for
                # anything unexpected, so one broken source can't stop the
                # rest of the sources in this tick from syncing.
                logger.exception("iCal sync job crashed for source %s", ical_source.id)


async def _send_checkin_reminders() -> None:
    """One tick of the scheduled job: emails every CONFIRMED booking whose
    check-in is today or tomorrow and that hasn't been reminded yet. Runs
    outside any request, so it opens its own session rather than depending
    on FastAPI's per-request get_db — same shape as _sync_all_sources."""
    async with async_session_factory() as session:
        booking_repository = BookingRepository(session)
        apartment_repository = ApartmentRepository(session)
        owner_repository = OwnerRepository(session)
        email_service = EmailService()

        today = date.today()
        tomorrow = today + timedelta(days=1)
        bookings = await booking_repository.list_pending_checkin_reminders(today, tomorrow)
        for booking in bookings:
            try:
                # apartment_id/owner_id are FKs with ondelete=RESTRICT, so
                # both are guaranteed to still exist while the booking does.
                apartment = await apartment_repository.get_by_id(booking.apartment_id)
                owner = await owner_repository.get_by_id(booking.owner_id)
                await email_service.send_checkin_reminder(booking, apartment, owner)
                # EmailService itself never raises (it logs and swallows any
                # send failure) — this try/except is a last-resort net for
                # anything else unexpected in this booking's processing, same
                # reasoning as _sync_all_sources's wrapping of sync_source.
                # Only marking sent_at when nothing raised means a real
                # failure here gets retried tomorrow instead of silently
                # never sending the reminder.
                booking.checkin_reminder_sent_at = datetime.now(timezone.utc)
                await booking_repository.update(booking)
            except Exception:
                logger.exception("Check-in reminder job crashed for booking %s", booking.id)


def start() -> None:
    scheduler.add_job(
        _sync_all_sources,
        "interval",
        hours=settings.ical_sync_interval_hours,
        id=_ICAL_SYNC_JOB_ID,
        replace_existing=True,
    )
    scheduler.add_job(
        _send_checkin_reminders,
        "cron",
        hour=9,
        id=_CHECKIN_REMINDERS_JOB_ID,
        replace_existing=True,
    )
    scheduler.start()


def shutdown() -> None:
    scheduler.shutdown(wait=False)
