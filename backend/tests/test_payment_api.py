import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import stripe
from httpx import AsyncClient

from app.models.booking import BookingStatus


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
    apartment = response.json()
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


async def _create_booking(client: AsyncClient, apartment_id: str, **overrides: object) -> dict:
    payload = {
        "apartment_id": apartment_id,
        "guest_full_name": "Jane Guest",
        "guest_email": "jane@example.com",
        "guest_count": 2,
        "check_in_date": str(date.today() + timedelta(days=10)),
        "check_out_date": str(date.today() + timedelta(days=15)),
    }
    payload.update(overrides)
    response = await client.post("/bookings", json=payload)
    assert response.status_code == 201
    return response.json()


def _patch_stripe_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _create(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            id="cs_test_api", url="https://checkout.stripe.com/c/pay/cs_test_api"
        )

    monkeypatch.setattr("stripe.checkout.Session.create", _create)


def _patch_construct_event(monkeypatch: pytest.MonkeyPatch, result: dict | Exception) -> None:
    def _construct_event(payload: bytes, sig_header: str, secret: str | None) -> dict:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("stripe.Webhook.construct_event", _construct_event)


async def test_create_checkout_session_returns_url(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Public — no headers sent when hitting the checkout-session endpoint,
    same reasoning as POST /bookings itself."""
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    _patch_stripe_checkout(monkeypatch)
    response = await client.post(f"/bookings/{booking['id']}/checkout-session")

    assert response.status_code == 200
    assert response.json() == {"checkout_url": "https://checkout.stripe.com/c/pay/cs_test_api"}


async def test_create_checkout_session_booking_not_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_stripe_checkout(monkeypatch)
    response = await client.post(f"/bookings/{uuid.uuid4()}/checkout-session")
    assert response.status_code == 404


async def test_create_checkout_session_non_pending_booking_rejected(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])
    await client.post(f"/bookings/{booking['id']}/confirm", headers=admin_headers)

    _patch_stripe_checkout(monkeypatch)
    response = await client.post(f"/bookings/{booking['id']}/checkout-session")
    assert response.status_code == 422


async def test_stripe_webhook_invalid_signature_returns_400(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_construct_event(
        monkeypatch, stripe.error.SignatureVerificationError("bad signature", "sig_header")
    )

    response = await client.post(
        "/webhooks/stripe", content=b"{}", headers={"stripe-signature": "not-real"}
    )
    assert response.status_code == 400


async def test_stripe_webhook_completed_event_confirms_booking(
    client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    _patch_stripe_checkout(monkeypatch)
    checkout_response = await client.post(f"/bookings/{booking['id']}/checkout-session")
    assert checkout_response.status_code == 200

    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_api", "payment_intent": "pi_test_api"}},
    }
    _patch_construct_event(monkeypatch, event)

    webhook_response = await client.post(
        "/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"}
    )
    assert webhook_response.status_code == 200

    booking_response = await client.get(f"/bookings/{booking['id']}", headers=admin_headers)
    assert booking_response.json()["status"] == BookingStatus.CONFIRMED.value


async def test_stripe_webhook_unhandled_event_type_returns_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_construct_event(
        monkeypatch, {"type": "payment_intent.created", "data": {"object": {"id": "pi_x"}}}
    )
    response = await client.post(
        "/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"}
    )
    assert response.status_code == 200
