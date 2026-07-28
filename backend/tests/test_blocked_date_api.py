import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Creates an Owner (via admin) and an owner-role User, links them
    directly at the ORM level (no public endpoint for that yet), and returns
    (owner_dict, that user's auth headers). Same pattern as
    test_authorization.py's helper of the same name."""
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


def _blocked_date_payload(**overrides: object) -> dict:
    payload = {
        "start_date": str(date.today() + timedelta(days=10)),
        "end_date": str(date.today() + timedelta(days=20)),
        "reason": "Owner maintenance",
    }
    payload.update(overrides)
    return payload


async def _create_blocked_date(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    response = await client.post(
        f"/api/v1/apartments/{apartment_id}/blocked-dates",
        json=_blocked_date_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_blocked_date(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    blocked_date = await _create_blocked_date(client, admin_headers, apartment["id"])
    assert blocked_date["apartment_id"] == apartment["id"]
    assert blocked_date["reason"] == "Owner maintenance"
    assert uuid.UUID(blocked_date["id"])


async def test_create_blocked_date_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/apartments/{uuid.uuid4()}/blocked-dates", json=_blocked_date_payload()
    )
    assert response.status_code == 401


async def test_create_blocked_date_apartment_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/apartments/{uuid.uuid4()}/blocked-dates",
        json=_blocked_date_payload(),
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_create_blocked_date_end_before_start_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/blocked-dates",
        json=_blocked_date_payload(
            start_date=str(date.today() + timedelta(days=20)),
            end_date=str(date.today() + timedelta(days=10)),
        ),
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_create_overlapping_blocked_date_returns_409(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_blocked_date(client, admin_headers, apartment["id"])

    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/blocked-dates",
        json=_blocked_date_payload(
            start_date=str(date.today() + timedelta(days=15)),
            end_date=str(date.today() + timedelta(days=25)),
        ),
        headers=admin_headers,
    )
    assert response.status_code == 409


async def test_list_blocked_dates(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    blocked_date = await _create_blocked_date(client, admin_headers, apartment["id"])

    response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/blocked-dates", headers=admin_headers
    )
    assert response.status_code == 200
    assert [b["id"] for b in response.json()] == [blocked_date["id"]]


async def test_update_blocked_date(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    blocked_date = await _create_blocked_date(client, admin_headers, apartment["id"])

    response = await client.patch(
        f"/api/v1/blocked-dates/{blocked_date['id']}",
        json={"reason": "Renovation"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "Renovation"


async def test_update_blocked_date_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/blocked-dates/{uuid.uuid4()}",
        json={"reason": "Renovation"},
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_delete_blocked_date(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    blocked_date = await _create_blocked_date(client, admin_headers, apartment["id"])

    response = await client.delete(
        f"/api/v1/blocked-dates/{blocked_date['id']}", headers=admin_headers
    )
    assert response.status_code == 204

    list_response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/blocked-dates", headers=admin_headers
    )
    assert list_response.json() == []


async def test_delete_blocked_date_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.delete(
        f"/api/v1/blocked-dates/{uuid.uuid4()}", headers=admin_headers
    )
    assert response.status_code == 404


# --- Authorization: owner cannot manage another owner's apartment's blocked dates ---


async def test_owner_cannot_create_blocked_date_for_other_owners_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/blocked-dates",
        json=_blocked_date_payload(),
        headers=other_owner_headers,
    )
    assert response.status_code == 403


async def test_owner_cannot_update_other_owners_blocked_date(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    blocked_date = await _create_blocked_date(client, admin_headers, apartment["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.patch(
        f"/api/v1/blocked-dates/{blocked_date['id']}",
        json={"reason": "Hostile takeover"},
        headers=other_owner_headers,
    )
    assert response.status_code == 403

    own_response = await client.patch(
        f"/api/v1/blocked-dates/{blocked_date['id']}",
        json={"reason": "Legitimate update"},
        headers=owner_headers,
    )
    assert own_response.status_code == 200


async def test_owner_cannot_delete_other_owners_blocked_date(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    blocked_date = await _create_blocked_date(client, admin_headers, apartment["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.delete(
        f"/api/v1/blocked-dates/{blocked_date['id']}", headers=other_owner_headers
    )
    assert response.status_code == 403
