import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from icalendar import Calendar
from sqlalchemy.exc import IntegrityError

from app.models.blocked_date import BlockedDate
from app.models.ical_source import IcalSource
from app.repositories.blocked_date import BlockedDateRepository

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT_SECONDS = 15.0


async def fetch_ical(url: str) -> bytes:
    """Separated out so tests can monkeypatch it instead of hitting the
    network — same pattern as app.core.storage.upload_photo."""
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _as_date(value: date | datetime) -> date:
    """VEVENT dtstart/dtend may arrive as a date or a datetime depending on
    how the source platform emits them — normalize to a plain date."""
    if isinstance(value, datetime):
        return value.date()
    return value


async def sync_source(
    ical_source: IcalSource, blocked_date_repository: BlockedDateRepository
) -> None:
    """Reconciles the BlockedDate rows previously imported from ical_source
    with what its feed currently reports: creates newly-appeared VEVENTs,
    deletes ones no longer present, and updates ones whose dates changed.

    Never raises: a fetch/parse failure or a per-event date conflict with
    another blocked date is recorded on ical_source.last_sync_error instead,
    so one bad source can never take down the sync run for the others (see
    app/core/scheduler.py, which syncs every source in a loop)."""
    # Captured up front and used everywhere below instead of re-reading
    # ical_source's attributes: a conflict further down triggers a rollback
    # inside blocked_date_repository.create()/update(), and SQLAlchemy
    # expires every object in the session on rollback regardless of
    # expire_on_commit — a later *synchronous* attribute read (e.g. in an
    # f-string or a constructor call, as opposed to something the ORM awaits
    # internally) would then crash with MissingGreenlet trying to lazy-load it.
    apartment_id = ical_source.apartment_id
    platform_name = ical_source.platform_name
    source_id = ical_source.id

    try:
        raw = await fetch_ical(ical_source.ical_url)
        calendar = Calendar.from_ical(raw)
    except Exception as exc:
        ical_source.last_sync_error = f"Could not fetch or parse iCal feed: {exc}"
        await blocked_date_repository.db.commit()
        await blocked_date_repository.db.refresh(ical_source)
        return

    feed_events: dict[str, tuple[date, date]] = {}
    for component in calendar.walk("VEVENT"):
        uid = str(component["uid"])
        dtstart = _as_date(component["dtstart"].dt)
        dtend = _as_date(component["dtend"].dt)
        feed_events[uid] = (dtstart, dtend)

    existing = await blocked_date_repository.list_by_ical_source(source_id)
    # Snapshot (object, start_date, end_date) per uid up front — same
    # expired-attribute hazard as above applies to these once a conflict
    # rolls back mid-loop, so nothing below reads dates off the ORM objects
    # directly.
    existing_by_uid = {
        blocked_date.external_uid: (blocked_date, blocked_date.start_date, blocked_date.end_date)
        for blocked_date in existing
    }

    # Removed on the source platform first, so a shifted date range on
    # another event doesn't spuriously conflict with a stale row that's
    # about to be deleted anyway.
    for uid, (blocked_date, _start, _end) in existing_by_uid.items():
        if uid not in feed_events:
            await blocked_date_repository.delete(blocked_date)

    conflict_messages: list[str] = []
    for uid, (dtstart, dtend) in feed_events.items():
        # dtend from iCal is exclusive; BlockedDate.end_date is inclusive —
        # exact inverse of the +1 day done in ical_export.py's export.
        new_start, new_end = dtstart, dtend - timedelta(days=1)
        entry = existing_by_uid.get(uid)

        if entry is None:
            blocked_date = BlockedDate(
                apartment_id=apartment_id,
                ical_source_id=source_id,
                external_uid=uid,
                start_date=new_start,
                end_date=new_end,
                reason=platform_name,
            )
            try:
                await blocked_date_repository.create(blocked_date)
            except IntegrityError as exc:
                message = f"Skipped event {uid}: overlaps an existing blocked date"
                logger.warning("iCal sync for source %s: %s (%s)", source_id, message, exc)
                conflict_messages.append(message)
        else:
            existing_blocked_date, old_start, old_end = entry
            if old_start != new_start or old_end != new_end:
                existing_blocked_date.start_date = new_start
                existing_blocked_date.end_date = new_end
                try:
                    await blocked_date_repository.update(existing_blocked_date)
                except IntegrityError as exc:
                    message = f"Skipped update for event {uid}: overlaps an existing blocked date"
                    logger.warning(
                        "iCal sync for source %s: %s (%s)", source_id, message, exc
                    )
                    conflict_messages.append(message)

    ical_source.last_synced_at = datetime.now(timezone.utc)
    ical_source.last_sync_error = "; ".join(conflict_messages) if conflict_messages else None
    await blocked_date_repository.db.commit()
    await blocked_date_repository.db.refresh(ical_source)
