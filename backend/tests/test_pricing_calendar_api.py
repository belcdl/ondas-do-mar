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
    response = await client.post("/api/v1/apartments", json=payload, headers=headers)
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
        f"/api/v1/apartments/{apartment_id}/rate-rules", json=payload, headers=headers
    )
    assert response.status_code == 201
    return response.json()


async def _create_blocked_date(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    payload = {
        "start_date": str(date.today() + timedelta(days=10)),
        "end_date": str(date.today() + timedelta(days=20)),
    }
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/apartments/{apartment_id}/blocked-dates", json=payload, headers=headers
    )
    assert response.status_code == 201
    return response.json()


def _booking_payload(apartment_id: str, **overrides: object) -> dict:
    payload = {
        "apartment_id": apartment_id,
        "guest_full_name": "Jane Guest",
        "guest_email": "jane@example.com",
        "guest_count": 2,
        "check_in_date": str(date.today() + timedelta(days=10)),
        "check_out_date": str(date.today() + timedelta(days=15)),
    }
    payload.update(overrides)
    return payload


async def _create_booking(client: AsyncClient, apartment_id: str, **overrides: object) -> dict:
    response = await client.post("/api/v1/bookings", json=_booking_payload(apartment_id, **overrides))
    assert response.status_code == 201
    return response.json()


async def _pricing_calendar(
    client: AsyncClient, apartment_id: str, from_date: date, to_date: date
):
    return await client.get(
        f"/api/v1/apartments/{apartment_id}/pricing-calendar",
        params={"from_date": str(from_date), "to_date": str(to_date)},
    )


async def test_pricing_calendar_returns_price_and_availability_per_day(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])

    from_date = date.today() + timedelta(days=30)
    to_date = from_date + timedelta(days=2)
    response = await _pricing_calendar(client, apartment["id"], from_date, to_date)

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {"date": str(from_date), "price": "120.00", "available": True},
        {"date": str(from_date + timedelta(days=1)), "price": "120.00", "available": True},
        {"date": str(from_date + timedelta(days=2)), "price": "120.00", "available": True},
    ]


async def test_pricing_calendar_day_without_rate_rule_has_null_price(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    from_date = date.today() + timedelta(days=40)
    await _create_rate_rule(
        client, admin_headers, apartment["id"], start_date=str(from_date), end_date=str(from_date)
    )

    response = await _pricing_calendar(
        client, apartment["id"], from_date, from_date + timedelta(days=1)
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["price"] == "120.00"
    assert body[1]["price"] is None
    assert body[1]["available"] is True


async def test_pricing_calendar_blocked_date_is_unavailable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    from_date = date.today() + timedelta(days=50)
    await _create_rate_rule(client, admin_headers, apartment["id"])
    await _create_blocked_date(
        client,
        admin_headers,
        apartment["id"],
        start_date=str(from_date + timedelta(days=1)),
        end_date=str(from_date + timedelta(days=2)),
    )

    response = await _pricing_calendar(
        client, apartment["id"], from_date, from_date + timedelta(days=3)
    )

    assert response.status_code == 200
    body = response.json()
    assert [d["available"] for d in body] == [True, False, False, True]
    # Still priced — blocking only affects availability, not the displayed price.
    assert body[1]["price"] == "120.00"


async def test_pricing_calendar_confirmed_booking_is_unavailable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])
    check_in = date.today() + timedelta(days=60)
    check_out = check_in + timedelta(days=2)
    booking = await _create_booking(
        client, apartment["id"], check_in_date=str(check_in), check_out_date=str(check_out)
    )
    confirm = await client.post(
        f"/api/v1/bookings/{booking['id']}/confirm", headers=admin_headers
    )
    assert confirm.status_code == 200

    response = await _pricing_calendar(client, apartment["id"], check_in, check_out)

    assert response.status_code == 200
    body = response.json()
    # check_out_date itself is exclusive (checkout day stays available).
    assert [d["available"] for d in body] == [False, False, True]
    assert all(d["price"] == "120.00" for d in body)


async def test_pricing_calendar_pending_booking_does_not_affect_availability(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])
    check_in = date.today() + timedelta(days=70)
    check_out = check_in + timedelta(days=2)
    await _create_booking(
        client, apartment["id"], check_in_date=str(check_in), check_out_date=str(check_out)
    )

    response = await _pricing_calendar(client, apartment["id"], check_in, check_out)

    assert response.status_code == 200
    assert all(d["available"] for d in response.json())


async def test_pricing_calendar_rejects_invalid_range(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    from_date = date.today() + timedelta(days=80)

    response = await _pricing_calendar(
        client, apartment["id"], from_date, from_date - timedelta(days=1)
    )

    assert response.status_code == 422


async def test_pricing_calendar_rejects_range_exceeding_max_days(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    from_date = date.today() + timedelta(days=90)

    response = await _pricing_calendar(
        client, apartment["id"], from_date, from_date + timedelta(days=400)
    )

    assert response.status_code == 422


async def test_pricing_calendar_apartment_not_found(client: AsyncClient) -> None:
    from_date = date.today()
    response = await _pricing_calendar(
        client, str(uuid.uuid4()), from_date, from_date + timedelta(days=1)
    )
    assert response.status_code == 404


async def test_pricing_calendar_inactive_apartment_returns_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])
    await client.post(f"/api/v1/apartments/{apartment['id']}/deactivate", headers=admin_headers)

    from_date = date.today()
    response = await _pricing_calendar(
        client, apartment["id"], from_date, from_date + timedelta(days=1)
    )

    assert response.status_code == 404


async def test_pricing_calendar_requires_no_authentication(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await _create_rate_rule(client, admin_headers, apartment["id"])

    from_date = date.today() + timedelta(days=100)
    response = await _pricing_calendar(
        client, apartment["id"], from_date, from_date + timedelta(days=1)
    )

    assert response.status_code == 200
