import uuid

from httpx import AsyncClient


async def _create_owner(client: AsyncClient, headers: dict[str, str], **overrides: str) -> dict:
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": "+34600000000",
    }
    payload.update(overrides)
    response = await client.post("/owners", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def test_create_owner(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    assert owner["is_active"] is True
    assert uuid.UUID(owner["id"])


async def test_create_owner_requires_admin(client: AsyncClient) -> None:
    response = await client.post(
        "/owners",
        json={"full_name": "Nope", "email": "nope@example.com"},
    )
    assert response.status_code == 401


async def test_create_owner_duplicate_email(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.post(
        "/owners",
        json={"full_name": "Other", "email": owner["email"]},
        headers=admin_headers,
    )
    assert response.status_code == 409


async def test_create_owner_validation_error(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/owners", json={"email": "missing-name@example.com"}, headers=admin_headers
    )
    assert response.status_code == 422


async def test_create_owner_full_name_too_long_returns_422_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """full_name is String(255) at the DB level; Pydantic has no max_length,
    so this exercises the DataError -> ValidationError translation."""
    response = await client.post(
        "/owners",
        json={"full_name": "A" * 500, "email": f"toolong-{uuid.uuid4()}@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_list_owners(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.get("/owners", headers=admin_headers)
    assert response.status_code == 200
    assert any(o["id"] == owner["id"] for o in response.json())


async def test_list_owners_requires_admin(client: AsyncClient) -> None:
    response = await client.get("/owners")
    assert response.status_code == 401


async def test_get_owner_by_id(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.get(f"/owners/{owner['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == owner["email"]


async def test_get_owner_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.get(f"/owners/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_update_owner(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.patch(
        f"/owners/{owner['id']}", json={"phone": "+34611111111"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+34611111111"


async def test_update_owner_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.patch(
        f"/owners/{uuid.uuid4()}", json={"phone": "+34611111111"}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_update_owner_duplicate_email(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner_a = await _create_owner(client, admin_headers)
    owner_b = await _create_owner(client, admin_headers)
    response = await client.patch(
        f"/owners/{owner_b['id']}", json={"email": owner_a["email"]}, headers=admin_headers
    )
    assert response.status_code == 409


async def test_deactivate_owner(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.post(f"/owners/{owner['id']}/deactivate", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    list_response = await client.get("/owners", headers=admin_headers)
    assert all(o["id"] != owner["id"] for o in list_response.json())


async def test_deactivate_owner_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(f"/owners/{uuid.uuid4()}/deactivate", headers=admin_headers)
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
    created = await client.post("/apartments", json=apartment_payload, headers=admin_headers)
    assert created.status_code == 201

    response = await client.get(f"/owners/{owner['id']}/apartments", headers=admin_headers)
    assert response.status_code == 200
    apartments = response.json()
    assert len(apartments) == 1
    assert apartments[0]["id"] == created.json()["id"]


async def test_list_owner_apartments_empty(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.get(f"/owners/{owner['id']}/apartments", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_list_owner_apartments_owner_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get(f"/owners/{uuid.uuid4()}/apartments", headers=admin_headers)
    assert response.status_code == 404
