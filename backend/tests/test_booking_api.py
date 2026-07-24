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
    client: AsyncClient,
    headers: dict[str, str],
    owner_id: str,
    *,
    with_rate_rule: bool = True,
    **overrides: str,
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
    apartment = response.json()
    if with_rate_rule:
        await _create_rate_rule(client, headers, apartment["id"])
    return apartment


async def _create_rate_rule(
    client: AsyncClient, headers: dict[str, str], apartment_id: str, **overrides: object
) -> dict:
    payload = {
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=400)),
        "price_per_night": "90.00",
        "min_stay": 1,
    }
    payload.update(overrides)
    response = await client.post(
        f"/apartments/{apartment_id}/rate-rules", json=payload, headers=headers
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
    """No headers — POST /bookings is public (guests have no accounts)."""
    response = await client.post("/bookings", json=_booking_payload(apartment_id, **overrides))
    assert response.status_code == 201
    return response.json()


async def test_create_booking(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """POST /bookings is intentionally public — no headers sent."""
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])
    assert booking["status"] == "pending"
    assert booking["owner_id"] == owner["id"]
    assert uuid.UUID(booking["id"])
    assert booking["confirmation_code"]


async def test_create_booking_apartment_not_found(client: AsyncClient) -> None:
    response = await client.post("/bookings", json=_booking_payload(str(uuid.uuid4())))
    assert response.status_code == 404


async def test_create_booking_inactive_owner(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    await client.post(f"/owners/{owner['id']}/deactivate", headers=admin_headers)

    response = await client.post("/bookings", json=_booking_payload(apartment["id"]))
    assert response.status_code == 422


async def test_create_booking_invalid_dates(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    response = await client.post(
        "/bookings",
        json=_booking_payload(
            apartment["id"],
            check_in_date=str(date.today() + timedelta(days=10)),
            check_out_date=str(date.today() + timedelta(days=5)),
        ),
    )
    assert response.status_code == 422


async def test_create_booking_validation_error(client: AsyncClient) -> None:
    response = await client.post("/bookings", json={"guest_email": "x@example.com"})
    assert response.status_code == 422


async def test_create_booking_zero_guest_count_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.post(
        "/bookings", json=_booking_payload(apartment["id"], guest_count=0)
    )
    assert response.status_code == 422


async def test_create_booking_client_supplied_total_price_is_ignored(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """BookingCreate has no total_price field — a client-supplied value is
    silently dropped (Pydantic's default extra="ignore"), never trusted.
    The booking still succeeds, priced entirely from the apartment's
    rate rule (90.00/night * 5 nights, per _create_rate_rule's defaults)."""
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"], total_price="999999.00")
    assert booking["total_price"] == "450.00"


async def test_create_booking_no_rate_rule_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"], with_rate_rule=False)
    response = await client.post("/bookings", json=_booking_payload(apartment["id"]))
    assert response.status_code == 422


async def test_create_booking_below_minimum_stay_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"], with_rate_rule=False)
    await _create_rate_rule(client, admin_headers, apartment["id"], min_stay=10)

    response = await client.post("/bookings", json=_booking_payload(apartment["id"]))
    assert response.status_code == 422


async def test_create_booking_guest_full_name_too_long_returns_422_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.post(
        "/bookings", json=_booking_payload(apartment["id"], guest_full_name="A" * 500)
    )
    assert response.status_code == 422


async def test_list_bookings_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/bookings")
    assert response.status_code == 401


async def test_list_bookings(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.get("/bookings", headers=admin_headers)
    assert response.status_code == 200
    assert any(b["id"] == booking["id"] for b in response.json())


async def test_list_bookings_filter_by_apartment(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment_a = await _create_apartment(client, admin_headers, owner["id"], name="A")
    apartment_b = await _create_apartment(client, admin_headers, owner["id"], name="B")
    booking_a = await _create_booking(client, apartment_a["id"])
    await _create_booking(client, apartment_b["id"])

    response = await client.get(
        "/bookings", params={"apartment_id": apartment_a["id"]}, headers=admin_headers
    )
    assert response.status_code == 200
    assert [b["id"] for b in response.json()] == [booking_a["id"]]


async def test_list_bookings_filter_by_status(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])
    await client.post(f"/bookings/{booking['id']}/confirm", headers=admin_headers)

    confirmed_response = await client.get(
        "/bookings", params={"status": "confirmed"}, headers=admin_headers
    )
    assert [b["id"] for b in confirmed_response.json()] == [booking["id"]]

    pending_response = await client.get(
        "/bookings", params={"status": "pending"}, headers=admin_headers
    )
    assert booking["id"] not in [b["id"] for b in pending_response.json()]


async def test_get_booking_by_id(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.get(f"/bookings/{booking['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["confirmation_code"] == booking["confirmation_code"]


async def test_get_booking_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.get(f"/bookings/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


async def test_update_booking(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.patch(
        f"/bookings/{booking['id']}", json={"guest_count": 4}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["guest_count"] == 4


async def test_update_booking_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        f"/bookings/{uuid.uuid4()}", json={"guest_count": 4}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_confirm_booking(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.post(f"/bookings/{booking['id']}/confirm", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["confirmed_at"] is not None


async def test_cancel_booking(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.post(f"/bookings/{booking['id']}/cancel", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_complete_booking(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])
    await client.post(f"/bookings/{booking['id']}/confirm", headers=admin_headers)

    response = await client.post(f"/bookings/{booking['id']}/complete", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


async def test_complete_pending_booking_fails(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.post(f"/bookings/{booking['id']}/complete", headers=admin_headers)
    assert response.status_code == 422


async def test_cancel_completed_booking_fails(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])
    await client.post(f"/bookings/{booking['id']}/confirm", headers=admin_headers)
    await client.post(f"/bookings/{booking['id']}/complete", headers=admin_headers)

    response = await client.post(f"/bookings/{booking['id']}/cancel", headers=admin_headers)
    assert response.status_code == 422


async def test_action_on_nonexistent_booking_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(f"/bookings/{uuid.uuid4()}/confirm", headers=admin_headers)
    assert response.status_code == 404


# --- Sprint 5.3: overlap protection ------------------------------------------------


async def test_confirming_overlapping_booking_returns_409(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    booking_a = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=20)),
        check_out_date=str(date.today() + timedelta(days=25)),
    )
    booking_b = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=22)),
        check_out_date=str(date.today() + timedelta(days=27)),
    )

    confirm_a = await client.post(f"/bookings/{booking_a['id']}/confirm", headers=admin_headers)
    assert confirm_a.status_code == 200

    confirm_b = await client.post(f"/bookings/{booking_b['id']}/confirm", headers=admin_headers)
    assert confirm_b.status_code == 409
    assert "not available" in confirm_b.json()["detail"]


async def test_pending_overlapping_bookings_can_both_be_created(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    booking_a = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=30)),
        check_out_date=str(date.today() + timedelta(days=35)),
    )
    booking_b = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=32)),
        check_out_date=str(date.today() + timedelta(days=37)),
    )

    assert booking_a["status"] == "pending"
    assert booking_b["status"] == "pending"


async def test_cancelled_booking_frees_dates_for_confirmation(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    booking_a = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=40)),
        check_out_date=str(date.today() + timedelta(days=45)),
    )
    booking_b = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=42)),
        check_out_date=str(date.today() + timedelta(days=47)),
    )

    await client.post(f"/bookings/{booking_a['id']}/confirm", headers=admin_headers)
    await client.post(f"/bookings/{booking_a['id']}/cancel", headers=admin_headers)

    confirm_b = await client.post(f"/bookings/{booking_b['id']}/confirm", headers=admin_headers)
    assert confirm_b.status_code == 200
    assert confirm_b.json()["status"] == "confirmed"


# --- Sprint 5.3: filters and confirmation-code lookup -------------------------------


async def test_list_bookings_filter_by_check_in_range(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(
        client,
        apartment["id"],
        check_in_date=str(date.today() + timedelta(days=60)),
        check_out_date=str(date.today() + timedelta(days=65)),
    )

    response = await client.get(
        "/bookings",
        params={
            "check_in_from": str(date.today() + timedelta(days=59)),
            "check_in_to": str(date.today() + timedelta(days=61)),
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert any(b["id"] == booking["id"] for b in response.json())

    empty_response = await client.get(
        "/bookings",
        params={"check_in_from": str(date.today() + timedelta(days=200))},
        headers=admin_headers,
    )
    assert all(b["id"] != booking["id"] for b in empty_response.json())


async def test_list_bookings_filter_by_guest_email_case_insensitive(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(
        client, apartment["id"], guest_email="Filter.Me@Example.com"
    )

    response = await client.get(
        "/bookings", params={"guest_email": "filter.me@example.com"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert any(b["id"] == booking["id"] for b in response.json())


async def test_get_booking_by_confirmation_code(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Public — no headers sent."""
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.get(f"/bookings/by-confirmation/{booking['confirmation_code']}")
    assert response.status_code == 200
    assert response.json()["id"] == booking["id"]

    lower_response = await client.get(
        f"/bookings/by-confirmation/{booking['confirmation_code'].lower()}"
    )
    assert lower_response.status_code == 200
    assert lower_response.json()["id"] == booking["id"]


async def test_get_booking_by_confirmation_code_not_found(client: AsyncClient) -> None:
    response = await client.get("/bookings/by-confirmation/NOPE0000")
    assert response.status_code == 404
