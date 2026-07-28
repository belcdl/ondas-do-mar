import uuid

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


async def test_create_owner(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    assert owner["is_active"] is True
    assert uuid.UUID(owner["id"])


async def test_create_owner_requires_admin(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/owners",
        json={"full_name": "Nope", "email": "nope@example.com"},
    )
    assert response.status_code == 401


async def test_create_owner_duplicate_email(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.post(
        "/api/v1/owners",
        json={"full_name": "Other", "email": owner["email"]},
        headers=admin_headers,
    )
    assert response.status_code == 409


async def test_create_owner_validation_error(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/owners", json={"email": "missing-name@example.com"}, headers=admin_headers
    )
    assert response.status_code == 422


async def test_create_owner_full_name_too_long_returns_422_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """full_name is String(255) at the DB level; Pydantic has no max_length,
    so this exercises the DataError -> ValidationError translation."""
    response = await client.post(
        "/api/v1/owners",
        json={"full_name": "A" * 500, "email": f"toolong-{uuid.uuid4()}@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_list_owners(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.get("/api/v1/owners", headers=admin_headers)
    assert response.status_code == 200
    assert any(o["id"] == owner["id"] for o in response.json())


async def test_list_owners_requires_admin(client: AsyncClient) -> None:
    response = await client.get("/api/v1/owners")
    assert response.status_code == 401


async def test_get_owner_by_id(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.get(f"/api/v1/owners/{owner['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == owner["email"]


async def test_get_owner_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.get(f"/api/v1/owners/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_update_owner(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.patch(
        f"/api/v1/owners/{owner['id']}", json={"phone": "+34611111111"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+34611111111"


async def test_update_owner_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.patch(
        f"/api/v1/owners/{uuid.uuid4()}", json={"phone": "+34611111111"}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_update_owner_duplicate_email(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner_a = await _create_owner(client, admin_headers)
    owner_b = await _create_owner(client, admin_headers)
    response = await client.patch(
        f"/api/v1/owners/{owner_b['id']}", json={"email": owner_a["email"]}, headers=admin_headers
    )
    assert response.status_code == 409


async def test_deactivate_owner(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.post(f"/api/v1/owners/{owner['id']}/deactivate", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    list_response = await client.get("/api/v1/owners", headers=admin_headers)
    assert all(o["id"] != owner["id"] for o in list_response.json())


async def test_deactivate_owner_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(f"/api/v1/owners/{uuid.uuid4()}/deactivate", headers=admin_headers)
    assert response.status_code == 404


async def test_list_owner_apartments(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment_payload = {
        "owner_id": owner["id"],
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    created = await client.post("/api/v1/apartments", json=apartment_payload, headers=admin_headers)
    assert created.status_code == 201

    response = await client.get(f"/api/v1/owners/{owner['id']}/apartments", headers=admin_headers)
    assert response.status_code == 200
    apartments = response.json()
    assert len(apartments) == 1
    assert apartments[0]["id"] == created.json()["id"]


async def test_list_owner_apartments_empty(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.get(f"/api/v1/owners/{owner['id']}/apartments", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_list_owner_apartments_owner_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get(f"/api/v1/owners/{uuid.uuid4()}/apartments", headers=admin_headers)
    assert response.status_code == 404


async def test_get_own_owner_profile(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    response = await client.get("/api/v1/owners/me", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["id"] == owner["id"]


async def test_get_own_owner_profile_admin_has_none(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """An admin has no linked Owner record — 404, not a crash."""
    response = await client.get("/api/v1/owners/me", headers=admin_headers)
    assert response.status_code == 404
