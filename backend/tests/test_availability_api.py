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
    response = await client.post("/owners", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_apartment(
    client: AsyncClient, headers: dict[str, str], owner_id: str, **overrides: object
) -> dict:
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    response = await client.post("/apartments", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_rate_rule(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    payload = {
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=400)),
        "price_per_night": "120.00",
        "min_stay": 1,
    }
    payload.update(overrides)
    response = await client.post(
        f"/apartments/{apartment_id}/rate-rules", json=payload, headers=headers
    )
    assert response.status_code == 201
    return response.json()


async def test_search_returns_available_apartment_with_price_breakdown(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])

    check_in = date.today() + timedelta(days=10)
    check_out = check_in + timedelta(days=3)
    response = await client.get(
        "/availability/search",
        params={"check_in": str(check_in), "check_out": str(check_out), "guests": 2},
    )
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 1
    result = results[0]
    assert result["apartment_id"] == apartment["id"]
    assert result["name"] == apartment["name"]
    assert result["guests"] == 2
    assert result["nights"] == 3
    assert result["currency"] == "EUR"
    assert result["price_total"] == "360.00"
    assert result["price_breakdown"] == [
        {"date": str(check_in), "price": "120.00"},
        {"date": str(check_in + timedelta(days=1)), "price": "120.00"},
        {"date": str(check_in + timedelta(days=2)), "price": "120.00"},
    ]


async def test_search_returns_empty_list_when_nothing_is_available(
    client: AsyncClient,
) -> None:
    check_in = date.today() + timedelta(days=10)
    check_out = check_in + timedelta(days=3)
    response = await client.get(
        "/availability/search",
        params={"check_in": str(check_in), "check_out": str(check_out), "guests": 2},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_search_excludes_apartment_with_insufficient_capacity(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"], max_guests=2)
    await _create_rate_rule(client, admin_headers, apartment["id"])

    check_in = date.today() + timedelta(days=15)
    response = await client.get(
        "/availability/search",
        params={
            "check_in": str(check_in),
            "check_out": str(check_in + timedelta(days=2)),
            "guests": 4,
        },
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_search_rejects_check_out_before_check_in(client: AsyncClient) -> None:
    check_in = date.today() + timedelta(days=10)
    response = await client.get(
        "/availability/search",
        params={
            "check_in": str(check_in),
            "check_out": str(check_in - timedelta(days=1)),
            "guests": 2,
        },
    )
    assert response.status_code == 422


async def test_search_requires_no_authentication(client: AsyncClient) -> None:
    """Public — matches the booking-creation endpoint's design (guests have no accounts)."""
    check_in = date.today() + timedelta(days=10)
    response = await client.get(
        "/availability/search",
        params={
            "check_in": str(check_in),
            "check_out": str(check_in + timedelta(days=1)),
            "guests": 1,
        },
    )
    assert response.status_code == 200
