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


async def test_create_owner(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    assert owner["is_active"] is True
    assert uuid.UUID(owner["id"])


async def test_create_owner_duplicate_email(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    response = await client.post("/owners", json={"full_name": "Other", "email": owner["email"]})
    assert response.status_code == 409


async def test_create_owner_validation_error(client: AsyncClient) -> None:
    response = await client.post("/owners", json={"email": "missing-name@example.com"})
    assert response.status_code == 422


async def test_list_owners(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    response = await client.get("/owners")
    assert response.status_code == 200
    assert any(o["id"] == owner["id"] for o in response.json())


async def test_get_owner_by_id(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    response = await client.get(f"/owners/{owner['id']}")
    assert response.status_code == 200
    assert response.json()["email"] == owner["email"]


async def test_get_owner_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/owners/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_update_owner(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    response = await client.patch(f"/owners/{owner['id']}", json={"phone": "+34611111111"})
    assert response.status_code == 200
    assert response.json()["phone"] == "+34611111111"


async def test_update_owner_not_found(client: AsyncClient) -> None:
    response = await client.patch(f"/owners/{uuid.uuid4()}", json={"phone": "+34611111111"})
    assert response.status_code == 404


async def test_update_owner_duplicate_email(client: AsyncClient) -> None:
    owner_a = await _create_owner(client)
    owner_b = await _create_owner(client)
    response = await client.patch(f"/owners/{owner_b['id']}", json={"email": owner_a["email"]})
    assert response.status_code == 409


async def test_deactivate_owner(client: AsyncClient) -> None:
    owner = await _create_owner(client)
    response = await client.post(f"/owners/{owner['id']}/deactivate")
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    list_response = await client.get("/owners")
    assert all(o["id"] != owner["id"] for o in list_response.json())


async def test_deactivate_owner_not_found(client: AsyncClient) -> None:
    response = await client.post(f"/owners/{uuid.uuid4()}/deactivate")
    assert response.status_code == 404
