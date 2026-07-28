import uuid

from httpx import AsyncClient


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


async def test_create_apartment(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    assert apartment["is_active"] is True
    assert apartment["owner_id"] == owner["id"]
    assert uuid.UUID(apartment["id"])


async def test_create_apartment_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/apartments",
        json={
            "owner_id": str(uuid.uuid4()),
            "name": "Ghost",
            "address_line": "Nowhere 1",
            "city": "Nowhere",
            "country": "Nowhere",
        },
    )
    assert response.status_code == 401


async def test_create_apartment_owner_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/apartments",
        json={
            "owner_id": str(uuid.uuid4()),
            "name": "Ghost",
            "address_line": "Nowhere 1",
            "city": "Nowhere",
            "country": "Nowhere",
        },
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_create_apartment_inactive_owner(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    await client.post(f"/api/v1/owners/{owner['id']}/deactivate", headers=admin_headers)

    response = await client.post(
        "/api/v1/apartments",
        json={
            "owner_id": owner["id"],
            "name": "Casa Azul",
            "address_line": "Rua da Praia 12",
            "city": "Porto",
            "country": "Portugal",
        },
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_create_apartment_validation_error(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post("/api/v1/apartments", json={"city": "Porto"}, headers=admin_headers)
    assert response.status_code == 422


async def test_list_apartments(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.get("/api/v1/apartments", headers=admin_headers)
    assert response.status_code == 200
    assert any(a["id"] == apartment["id"] for a in response.json())


async def test_get_apartment_by_id(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.get(f"/api/v1/apartments/{apartment['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == apartment["name"]


async def test_get_apartment_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.get(f"/api/v1/apartments/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_update_apartment(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.patch(
        f"/api/v1/apartments/{apartment['id']}", json={"bedrooms": 3}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["bedrooms"] == 3


async def test_update_apartment_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/apartments/{uuid.uuid4()}", json={"bedrooms": 3}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_update_apartment_reassign_owner(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner_a = await _create_owner(client, admin_headers)
    owner_b = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner_a["id"])

    response = await client.patch(
        f"/api/v1/apartments/{apartment['id']}",
        json={"owner_id": owner_b["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["owner_id"] == owner_b["id"]


async def test_update_apartment_reassign_to_inactive_owner(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner_a = await _create_owner(client, admin_headers)
    owner_b = await _create_owner(client, admin_headers)
    await client.post(f"/api/v1/owners/{owner_b['id']}/deactivate", headers=admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner_a["id"])

    response = await client.patch(
        f"/api/v1/apartments/{apartment['id']}",
        json={"owner_id": owner_b["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_deactivate_apartment(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/deactivate", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    list_response = await client.get("/api/v1/apartments", headers=admin_headers)
    assert all(a["id"] != apartment["id"] for a in list_response.json())


async def test_deactivate_apartment_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(f"/api/v1/apartments/{uuid.uuid4()}/deactivate", headers=admin_headers)
    assert response.status_code == 404
