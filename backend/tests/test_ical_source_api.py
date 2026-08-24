import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocked_date import BlockedDate
from app.models.user import UserRole
from app.repositories.owner import OwnerRepository
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService
from tests.conftest import auth_headers_for


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


async def _make_owner_with_linked_user(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    **overrides: str,
) -> tuple[dict, dict[str, str]]:
    """Same pattern as test_blocked_date_api.py's helper of the same name."""
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


def _ical_source_payload(**overrides: object) -> dict:
    payload = {
        "platform_name": "Booking.com",
        "ical_url": "https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123",
    }
    payload.update(overrides)
    return payload


async def _create_ical_source(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    response = await client.post(
        f"/api/v1/apartments/{apartment_id}/ical-sources",
        json=_ical_source_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_ical_source(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    assert ical_source["apartment_id"] == apartment["id"]
    assert ical_source["platform_name"] == "Booking.com"
    assert ical_source["ical_url"] == "https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123"
    assert ical_source["last_synced_at"] is None
    assert ical_source["last_sync_error"] is None
    assert uuid.UUID(ical_source["id"])


async def test_create_ical_source_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/apartments/{uuid.uuid4()}/ical-sources", json=_ical_source_payload()
    )
    assert response.status_code == 401


async def test_create_ical_source_apartment_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/apartments/{uuid.uuid4()}/ical-sources",
        json=_ical_source_payload(),
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_create_ical_source_rejects_invalid_url(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/ical-sources",
        json=_ical_source_payload(ical_url="not-a-url"),
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_list_ical_sources(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/ical-sources", headers=admin_headers
    )
    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [ical_source["id"]]


async def test_update_ical_source(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    response = await client.patch(
        f"/api/v1/ical-sources/{ical_source['id']}",
        json={"platform_name": "Airbnb"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["platform_name"] == "Airbnb"


async def test_update_ical_source_rejects_invalid_url(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    response = await client.patch(
        f"/api/v1/ical-sources/{ical_source['id']}",
        json={"ical_url": "not-a-url"},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_update_ical_source_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/ical-sources/{uuid.uuid4()}",
        json={"platform_name": "Airbnb"},
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_delete_ical_source(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    response = await client.delete(
        f"/api/v1/ical-sources/{ical_source['id']}", headers=admin_headers
    )
    assert response.status_code == 204

    list_response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/ical-sources", headers=admin_headers
    )
    assert list_response.json() == []


async def test_delete_ical_source_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.delete(f"/api/v1/ical-sources/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_delete_ical_source_cascades_to_imported_blocked_dates(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """A BlockedDate imported from this source (ical_source_id set) must be
    deleted automatically when the source is deleted — no CRUD endpoint sets
    ical_source_id (that's step 2's sync job), so it's created directly at
    the ORM level here, same as the FK ondelete=CASCADE it's exercising."""
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    blocked_date = BlockedDate(
        apartment_id=uuid.UUID(apartment["id"]),
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=32),
        ical_source_id=uuid.UUID(ical_source["id"]),
        external_uid="event-123@booking.com",
    )
    db_session.add(blocked_date)
    await db_session.commit()
    blocked_date_id = blocked_date.id

    response = await client.delete(
        f"/api/v1/ical-sources/{ical_source['id']}", headers=admin_headers
    )
    assert response.status_code == 204

    # The row was removed by the DB's ON DELETE CASCADE, not by the ORM, so
    # db_session.get() would just return the stale identity-mapped object
    # without hitting the DB — a fresh SELECT is needed to observe it.
    result = await db_session.execute(select(BlockedDate).where(BlockedDate.id == blocked_date_id))
    assert result.scalar_one_or_none() is None


# --- Authorization: owner cannot manage another owner's apartment's iCal sources ---


async def test_owner_cannot_create_ical_source_for_other_owners_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/ical-sources",
        json=_ical_source_payload(),
        headers=other_owner_headers,
    )
    assert response.status_code == 403


async def test_owner_cannot_update_other_owners_ical_source(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.patch(
        f"/api/v1/ical-sources/{ical_source['id']}",
        json={"platform_name": "Hostile takeover"},
        headers=other_owner_headers,
    )
    assert response.status_code == 403

    own_response = await client.patch(
        f"/api/v1/ical-sources/{ical_source['id']}",
        json={"platform_name": "Legitimate update"},
        headers=owner_headers,
    )
    assert own_response.status_code == 200


async def test_owner_cannot_delete_other_owners_ical_source(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    ical_source = await _create_ical_source(client, admin_headers, apartment["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.delete(
        f"/api/v1/ical-sources/{ical_source['id']}", headers=other_owner_headers
    )
    assert response.status_code == 403
