import uuid
from datetime import date, timedelta

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


def _rate_rule_payload(**overrides: object) -> dict:
    payload = {
        "start_date": str(date.today() + timedelta(days=10)),
        "end_date": str(date.today() + timedelta(days=20)),
        "price_per_night": "90.00",
        "min_stay": 1,
    }
    payload.update(overrides)
    return payload


async def _create_rate_rule(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    response = await client.post(
        f"/api/v1/apartments/{apartment_id}/rate-rules",
        json=_rate_rule_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_rate_rule(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    rate_rule = await _create_rate_rule(client, admin_headers, apartment["id"])
    assert rate_rule["apartment_id"] == apartment["id"]
    assert rate_rule["min_stay"] == 1
    assert uuid.UUID(rate_rule["id"])


async def test_create_rate_rule_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/apartments/{uuid.uuid4()}/rate-rules", json=_rate_rule_payload()
    )
    assert response.status_code == 401


async def test_create_rate_rule_apartment_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/apartments/{uuid.uuid4()}/rate-rules", json=_rate_rule_payload(), headers=admin_headers
    )
    assert response.status_code == 404


async def test_create_rate_rule_end_before_start_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/rate-rules",
        json=_rate_rule_payload(
            start_date=str(date.today() + timedelta(days=20)),
            end_date=str(date.today() + timedelta(days=10)),
        ),
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_create_overlapping_rate_rule_returns_409(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])

    response = await client.post(
        f"/api/v1/apartments/{apartment['id']}/rate-rules",
        json=_rate_rule_payload(
            start_date=str(date.today() + timedelta(days=15)),
            end_date=str(date.today() + timedelta(days=25)),
        ),
        headers=admin_headers,
    )
    assert response.status_code == 409


async def test_list_rate_rules(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    rate_rule = await _create_rate_rule(client, admin_headers, apartment["id"])

    response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/rate-rules", headers=admin_headers
    )
    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [rate_rule["id"]]


async def test_update_rate_rule(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    rate_rule = await _create_rate_rule(client, admin_headers, apartment["id"])

    response = await client.patch(
        f"/api/v1/rate-rules/{rate_rule['id']}",
        json={"price_per_night": "150.00"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["price_per_night"] == "150.00"


async def test_update_rate_rule_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/rate-rules/{uuid.uuid4()}", json={"price_per_night": "150.00"}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_delete_rate_rule(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    rate_rule = await _create_rate_rule(client, admin_headers, apartment["id"])

    response = await client.delete(f"/api/v1/rate-rules/{rate_rule['id']}", headers=admin_headers)
    assert response.status_code == 204

    list_response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/rate-rules", headers=admin_headers
    )
    assert list_response.json() == []


async def test_delete_rate_rule_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.delete(f"/api/v1/rate-rules/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_delete_rate_rule_blocked_by_confirmed_booking(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    rate_rule = await _create_rate_rule(client, admin_headers, apartment["id"])

    booking_response = await client.post(
        "/api/v1/bookings",
        json={
            "apartment_id": apartment["id"],
            "guest_full_name": "Jane Guest",
            "guest_email": "jane@example.com",
            "guest_count": 2,
            "check_in_date": str(date.today() + timedelta(days=12)),
            "check_out_date": str(date.today() + timedelta(days=15)),
        },
    )
    assert booking_response.status_code == 201
    booking = booking_response.json()
    await client.post(f"/api/v1/bookings/{booking['id']}/confirm", headers=admin_headers)

    response = await client.delete(f"/api/v1/rate-rules/{rate_rule['id']}", headers=admin_headers)
    assert response.status_code == 409
