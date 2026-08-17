import uuid

import pytest
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


async def test_create_apartment_with_amenities(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(
        client,
        admin_headers,
        owner["id"],
        amenities=["wifi", "tv"],
        amenities_other="Portable air conditioning unit",
    )
    assert apartment["amenities"] == ["wifi", "tv"]
    assert apartment["amenities_other"] == "Portable air conditioning unit"


async def test_create_apartment_defaults_to_no_amenities(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    assert apartment["amenities"] == []
    assert apartment["amenities_other"] is None


async def test_update_apartment_amenities(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"], amenities=["wifi"])

    response = await client.patch(
        f"/api/v1/apartments/{apartment['id']}",
        json={"amenities": ["pets_allowed", "terrace"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["amenities"] == ["pets_allowed", "terrace"]


async def test_get_apartment_public(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.core.storage.upload_photo", lambda *args, **kwargs: None)
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(
        client, admin_headers, owner["id"], amenities=["wifi", "tv"]
    )
    photo_1 = await client.post(
        f"/api/v1/apartments/{apartment['id']}/photos",
        files={"file": ("a.jpg", b"fake-image-bytes-1", "image/jpeg")},
        headers=admin_headers,
    )
    photo_2 = await client.post(
        f"/api/v1/apartments/{apartment['id']}/photos",
        files={"file": ("b.jpg", b"fake-image-bytes-2", "image/jpeg")},
        headers=admin_headers,
    )
    assert photo_1.status_code == 201
    assert photo_2.status_code == 201

    response = await client.get(f"/api/v1/apartments/{apartment['id']}/public")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == apartment["id"]
    assert body["name"] == apartment["name"]
    assert body["address_line"] == apartment["address_line"]
    assert body["city"] == apartment["city"]
    assert body["country"] == apartment["country"]
    assert body["amenities"] == ["wifi", "tv"]
    assert body["photos"] == [photo_1.json()["url"], photo_2.json()["url"]]
    assert "owner_id" not in body


async def test_get_apartment_public_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/apartments/{uuid.uuid4()}/public")
    assert response.status_code == 404


async def test_get_apartment_public_inactive_returns_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await client.post(f"/api/v1/apartments/{apartment['id']}/deactivate", headers=admin_headers)

    response = await client.get(f"/api/v1/apartments/{apartment['id']}/public")
    assert response.status_code == 404


async def test_create_apartment_invalid_amenity_returns_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    response = await client.post(
        "/api/v1/apartments",
        json={
            "owner_id": owner["id"],
            "name": "Casa Azul",
            "address_line": "Rua da Praia 12",
            "city": "Porto",
            "country": "Portugal",
            "amenities": ["not_a_real_amenity"],
        },
        headers=admin_headers,
    )
    assert response.status_code == 422
