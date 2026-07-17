import uuid

from httpx import AsyncClient


async def _create_owner(client: AsyncClient, **overrides: str) -> dict:
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": "+34600000000",
    }
    payload.update(overrides)
    response = await client.post("/owners", json=payload)
    assert response.status_code == 201
    return response.json()


async def _create_apartment(client: AsyncClient, owner_id: str, **overrides: str) -> dict:
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    response = await client.post("/apartments", json=payload)
    assert response.status_code == 201
    return response.json()


async def test_create_apartment(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    apartment = await _create_apartment(client, owner["id"])
    assert apartment["is_active"] is True
    assert apartment["owner_id"] == owner["id"]
    assert uuid.UUID(apartment["id"])


async def test_create_apartment_owner_not_found(client: AsyncClient) -> None:
    response = await client.post(
        "/apartments",
        json={
            "owner_id": str(uuid.uuid4()),
            "name": "Ghost",
            "address_line": "Nowhere 1",
            "city": "Nowhere",
            "country": "Nowhere",
        },
    )
    assert response.status_code == 404


async def test_create_apartment_inactive_owner(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    await client.post(f"/owners/{owner['id']}/deactivate")

    response = await client.post(
        "/apartments",
        json={
            "owner_id": owner["id"],
            "name": "Casa Azul",
            "address_line": "Rua da Praia 12",
            "city": "Porto",
            "country": "Portugal",
        },
    )
    assert response.status_code == 422


async def test_create_apartment_validation_error(client: AsyncClient) -> None:
    response = await client.post("/apartments", json={"city": "Porto"})
    assert response.status_code == 422


async def test_list_apartments(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    apartment = await _create_apartment(client, owner["id"])
    response = await client.get("/apartments")
    assert response.status_code == 200
    assert any(a["id"] == apartment["id"] for a in response.json())


async def test_get_apartment_by_id(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    apartment = await _create_apartment(client, owner["id"])
    response = await client.get(f"/apartments/{apartment['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == apartment["name"]


async def test_get_apartment_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/apartments/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_update_apartment(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    apartment = await _create_apartment(client, owner["id"])
    response = await client.patch(f"/apartments/{apartment['id']}", json={"bedrooms": 3})
    assert response.status_code == 200
    assert response.json()["bedrooms"] == 3


async def test_update_apartment_not_found(client: AsyncClient) -> None:
    response = await client.patch(f"/apartments/{uuid.uuid4()}", json={"bedrooms": 3})
    assert response.status_code == 404


async def test_update_apartment_reassign_owner(client: AsyncClient) -> None:
    owner_a = await _create_owner(client)
    owner_b = await _create_owner(client)
    apartment = await _create_apartment(client, owner_a["id"])

    response = await client.patch(
        f"/apartments/{apartment['id']}", json={"owner_id": owner_b["id"]}
    )
    assert response.status_code == 200
    assert response.json()["owner_id"] == owner_b["id"]


async def test_update_apartment_reassign_to_inactive_owner(client: AsyncClient) -> None:
    owner_a = await _create_owner(client)
    owner_b = await _create_owner(client)
    await client.post(f"/owners/{owner_b['id']}/deactivate")
    apartment = await _create_apartment(client, owner_a["id"])

    response = await client.patch(
        f"/apartments/{apartment['id']}", json={"owner_id": owner_b["id"]}
    )
    assert response.status_code == 422


async def test_deactivate_apartment(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    apartment = await _create_apartment(client, owner["id"])
    response = await client.post(f"/apartments/{apartment['id']}/deactivate")
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    list_response = await client.get("/apartments")
    assert all(a["id"] != apartment["id"] for a in list_response.json())


async def test_deactivate_apartment_not_found(client: AsyncClient) -> None:
    response = await client.post(f"/apartments/{uuid.uuid4()}/deactivate")
    assert response.status_code == 404
