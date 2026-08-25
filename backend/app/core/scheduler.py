import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.ical_source import IcalSourceRepository
from app.services.ical_sync import sync_source

logger = logging.getLogger(__name__)

settings = get_settings()

scheduler = AsyncIOScheduler()

_JOB_ID = "ical_sync"


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


def start() -> None:
    scheduler.add_job(
        _sync_all_sources,
        "interval",
        hours=settings.ical_sync_interval_hours,
        id=_JOB_ID,
        replace_existing=True,
    )
    scheduler.start()


def shutdown() -> None:
    scheduler.shutdown(wait=False)
