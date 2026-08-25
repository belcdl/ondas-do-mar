import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from icalendar import Calendar, Event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from app.repositories.apartment import ApartmentRepository
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.ical_source import IcalSourceRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.blocked_date import BlockedDateCreate
from app.schemas.ical_source import IcalSourceCreate
from app.schemas.owner import OwnerCreate
from app.schemas.user import UserCreate
from app.services import ical_sync
from app.services.apartment import ApartmentService
from app.services.blocked_date import BlockedDateService
from app.services.ical_source import IcalSourceService
from app.services.owner import OwnerService
from app.services.user import UserService
from tests.conftest import auth_headers_for

# --- service-level fixtures (mirrors test_ical_export_api.py's pattern) ---


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


async def _make_apartment(db_session: AsyncSession, owner_id: uuid.UUID, **overrides: str):
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


async def _make_ical_source(db_session: AsyncSession, apartment_id: uuid.UUID, **overrides: str):
    service = IcalSourceService(IcalSourceRepository(db_session))
    payload = {
        "platform_name": "Booking.com",
        "ical_url": "https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123",
    }
    payload.update(overrides)
    return await service.create_ical_source(IcalSourceCreate(apartment_id=apartment_id, **payload))


def _build_ics(events: list[tuple[str, date, date]]) -> bytes:
    """Builds a real .ics payload with icalendar rather than a hardcoded
    string, so it stays valid if icalendar's exact serialization ever
    changes."""
    calendar = Calendar()
    calendar.add("prodid", "-//Test Platform//EN")
    calendar.add("version", "2.0")
    for uid, dtstart, dtend in events:
        event = Event()
        event.add("uid", uid)
        event.add("dtstart", dtstart)
        event.add("dtend", dtend)
        calendar.add_component(event)
    return calendar.to_ical()


def _fetch_returning(payload: bytes):
    async def _fetch(url: str) -> bytes:
        return payload

    return _fetch


# --- sync_source ---


async def test_sync_source_creates_blocked_dates_from_new_events(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    ical_source = await _make_ical_source(db_session, apartment.id)

    ics_bytes = _build_ics(
        [
            ("event-1@booking.com", date(2026, 10, 1), date(2026, 10, 4)),
            ("event-2@booking.com", date(2026, 11, 1), date(2026, 11, 3)),
        ]
    )
    monkeypatch.setattr(ical_sync, "fetch_ical", _fetch_returning(ics_bytes))

    repo = BlockedDateRepository(db_session)
    await ical_sync.sync_source(ical_source, repo)

    blocked_dates = await repo.list_by_ical_source(ical_source.id)
    assert len(blocked_dates) == 2
    by_uid = {bd.external_uid: bd for bd in blocked_dates}

    # dtstart=2026-10-01, dtend=2026-10-04 (exclusive) -> end_date=2026-10-03 (inclusive)
    event_1 = by_uid["event-1@booking.com"]
    assert event_1.start_date == date(2026, 10, 1)
    assert event_1.end_date == date(2026, 10, 3)
    assert event_1.ical_source_id == ical_source.id
    assert event_1.reason == "Booking.com"

    event_2 = by_uid["event-2@booking.com"]
    assert event_2.start_date == date(2026, 11, 1)
    assert event_2.end_date == date(2026, 11, 2)

    assert ical_source.last_synced_at is not None
    assert ical_source.last_sync_error is None


async def test_sync_source_deletes_blocked_date_when_event_removed_from_feed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    ical_source = await _make_ical_source(db_session, apartment.id)
    repo = BlockedDateRepository(db_session)

    first_feed = _build_ics(
        [
            ("event-1@booking.com", date(2026, 10, 1), date(2026, 10, 4)),
            ("event-2@booking.com", date(2026, 11, 1), date(2026, 11, 3)),
        ]
    )
    monkeypatch.setattr(ical_sync, "fetch_ical", _fetch_returning(first_feed))
    await ical_sync.sync_source(ical_source, repo)
    assert len(await repo.list_by_ical_source(ical_source.id)) == 2

    # event-1 no longer in the feed — its BlockedDate must be removed;
    # event-2 is untouched.
    second_feed = _build_ics([("event-2@booking.com", date(2026, 11, 1), date(2026, 11, 3))])
    monkeypatch.setattr(ical_sync, "fetch_ical", _fetch_returning(second_feed))
    await ical_sync.sync_source(ical_source, repo)

    blocked_dates = await repo.list_by_ical_source(ical_source.id)
    assert [bd.external_uid for bd in blocked_dates] == ["event-2@booking.com"]


async def test_sync_source_skips_event_overlapping_existing_blocked_date(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    ical_source = await _make_ical_source(db_session, apartment.id)

    blocked_date_service = BlockedDateService(BlockedDateRepository(db_session))
    await blocked_date_service.create_blocked_date(
        BlockedDateCreate(
            apartment_id=apartment.id,
            start_date=date(2026, 10, 2),
            end_date=date(2026, 10, 5),
            reason="Owner maintenance",
        )
    )

    ics_bytes = _build_ics(
        [
            # 2026-10-01..2026-10-03 inclusive — overlaps the manual block above.
            ("event-overlap@booking.com", date(2026, 10, 1), date(2026, 10, 4)),
            ("event-ok@booking.com", date(2026, 12, 1), date(2026, 12, 3)),
        ]
    )
    monkeypatch.setattr(ical_sync, "fetch_ical", _fetch_returning(ics_bytes))

    repo = BlockedDateRepository(db_session)
    await ical_sync.sync_source(ical_source, repo)

    blocked_dates = await repo.list_by_ical_source(ical_source.id)
    assert [bd.external_uid for bd in blocked_dates] == ["event-ok@booking.com"]

    assert ical_source.last_synced_at is not None
    assert ical_source.last_sync_error is not None
    assert "event-overlap@booking.com" in ical_source.last_sync_error


async def test_sync_source_records_error_without_raising_when_fetch_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    ical_source = await _make_ical_source(db_session, apartment.id)
    assert ical_source.last_synced_at is None

    async def _failing_fetch(url: str) -> bytes:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ical_sync, "fetch_ical", _failing_fetch)

    repo = BlockedDateRepository(db_session)
    await ical_sync.sync_source(ical_source, repo)  # must not raise

    assert ical_source.last_synced_at is None
    assert ical_source.last_sync_error is not None
    assert "connection refused" in ical_source.last_sync_error


# --- POST /ical-sources/{id}/sync-now ---


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


async def _create_ical_source(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    payload = {
        "platform_name": "Booking.com",
        "ical_url": "https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123",
    }
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/apartments/{apartment_id}/ical-sources", json=payload, headers=headers
    )
    assert response.status_code == 201
    return response.json()


async def _make_owner_with_linked_user(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    **overrides: str,
) -> tuple[dict, dict[str, str]]:
    """Same pattern as test_ical_source_api.py's helper of the same name."""
    owner = await _create_owner(client, admin_headers, **overrides)
    user = await UserService(UserRepository(db_session)).create_user(
        UserCreate(
            email=f"owner-user-{uuid.uuid4()}@example.com",
            password="Sup3rSecret!",
            full_name="Owner User",
            role=UserRole.OWNER,
        )
    )
    owner_repo = OwnerRepository(db_session)
    owner_obj = await owner_repo.get_by_id(uuid.UUID(owner["id"]))
    assert owner_obj is not None
    owner_obj.user_id = user.id
    db_session.add(owner_obj)
    await db_session.commit()
    return owner, auth_headers_for(user)


async def test_sync_now_endpoint_success(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    ics_bytes = _build_ics([("event-1@booking.com", date(2026, 10, 1), date(2026, 10, 4))])
    monkeypatch.setattr(ical_sync, "fetch_ical", _fetch_returning(ics_bytes))

    response = await client.post(
        f"/api/v1/ical-sources/{ical_source['id']}/sync-now", headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["last_synced_at"] is not None
    assert body["last_sync_error"] is None


async def test_sync_now_endpoint_requires_ownership(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.post(
        f"/api/v1/ical-sources/{ical_source['id']}/sync-now", headers=other_owner_headers
    )
    assert response.status_code == 403
