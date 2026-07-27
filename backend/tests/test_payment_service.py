import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BookingStatus
from app.models.payment import PaymentStatus
from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.payment import PaymentRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.booking import BookingCreate
from app.schemas.owner import OwnerCreate
from app.schemas.rate_rule import RateRuleCreate
from app.services.apartment import ApartmentService
from app.services.booking import BookingService
from app.services.owner import OwnerService
from app.services.payment import (
    BookingNotPayableError,
    InvalidWebhookSignatureError,
    PaymentService,
)
from app.services.rate_rule import RateRuleService


def _owner_service(db_session: AsyncSession) -> OwnerService:
    return OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )


async def _make_owner(db_session: AsyncSession, **overrides: str | None):
    service = _owner_service(db_session)
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": None,
    }
    payload.update(overrides)
    return await service.create_owner(OwnerCreate(**payload))


async def _make_apartment(db_session: AsyncSession, owner_id: uuid.UUID, **overrides: object):
    service = ApartmentService(ApartmentRepository(db_session), OwnerRepository(db_session))
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    return await service.create_apartment(ApartmentCreate(**payload))


def _rate_rule_service(db_session: AsyncSession) -> RateRuleService:
    return RateRuleService(RateRuleRepository(db_session), BookingRepository(db_session))


async def _make_rate_rule(db_session: AsyncSession, apartment_id: uuid.UUID, **overrides: object):
    service = _rate_rule_service(db_session)
    payload = {
        "apartment_id": apartment_id,
        "start_date": date.today(),
        "end_date": date.today() + timedelta(days=400),
        "price_per_night": Decimal("90.00"),
        "min_stay": 1,
    }
    payload.update(overrides)
    return await service.create_rate_rule(RateRuleCreate(**payload))


def _booking_service(db_session: AsyncSession) -> BookingService:
    return BookingService(
        BookingRepository(db_session),
        ApartmentRepository(db_session),
        OwnerRepository(db_session),
        _rate_rule_service(db_session),
    )


def _booking_payload(apartment_id: uuid.UUID, **overrides: object) -> BookingCreate:
    payload = {
        "apartment_id": apartment_id,
        "guest_full_name": "Jane Guest",
        "guest_email": "jane@example.com",
        "guest_phone": None,
        "guest_count": 2,
        "check_in_date": date.today() + timedelta(days=10),
        "check_out_date": date.today() + timedelta(days=15),
    }
    payload.update(overrides)
    return BookingCreate(**payload)


def _payment_service(db_session: AsyncSession) -> PaymentService:
    return PaymentService(
        PaymentRepository(db_session),
        ApartmentRepository(db_session),
        _booking_service(db_session),
    )


class _FakeStripeCheckout:
    """Records every call made to stripe.checkout.Session.create and returns
    a fake session with an incrementing id, so a test can assert both what
    was sent to Stripe and that a retry produces a distinct session."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        session_id = f"cs_test_{len(self.calls)}"
        return SimpleNamespace(
            id=session_id, url=f"https://checkout.stripe.com/c/pay/{session_id}"
        )


def _patch_stripe_checkout(monkeypatch: pytest.MonkeyPatch) -> _FakeStripeCheckout:
    fake = _FakeStripeCheckout()
    monkeypatch.setattr("stripe.checkout.Session.create", fake.create)
    return fake


def _patch_construct_event(monkeypatch: pytest.MonkeyPatch, result: dict | Exception) -> None:
    def _construct_event(payload: bytes, sig_header: str, secret: str | None) -> dict:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("stripe.Webhook.construct_event", _construct_event)


def _completed_event(checkout_session_id: str, payment_intent_id: str) -> dict:
    return {
        "type": "checkout.session.completed",
        "data": {"object": {"id": checkout_session_id, "payment_intent": payment_intent_id}},
    }


async def test_create_checkout_session_creates_pending_payment(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id, price_per_night=Decimal("120.00"))
    booking = await _booking_service(db_session).create_booking(_booking_payload(apartment.id))

    fake = _patch_stripe_checkout(monkeypatch)
    service = _payment_service(db_session)
    checkout_url = await service.create_checkout_session(booking.id)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["line_items"][0]["price_data"]["unit_amount"] == int(booking.total_price * 100)
    assert call["line_items"][0]["price_data"]["currency"] == booking.currency.lower()
    assert call["metadata"]["booking_id"] == str(booking.id)
    assert checkout_url == "https://checkout.stripe.com/c/pay/cs_test_1"

    payment = await PaymentRepository(db_session).get_by_booking_id(booking.id)
    assert payment is not None
    assert payment.status == PaymentStatus.PENDING
    assert payment.stripe_checkout_session_id == "cs_test_1"
    assert payment.amount == booking.total_price
    assert payment.currency == booking.currency


async def test_create_checkout_session_non_pending_booking_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    booking_service = _booking_service(db_session)
    booking = await booking_service.create_booking(_booking_payload(apartment.id))
    await booking_service.confirm_booking(booking.id)

    _patch_stripe_checkout(monkeypatch)
    service = _payment_service(db_session)

    with pytest.raises(BookingNotPayableError):
        await service.create_checkout_session(booking.id)


async def test_create_checkout_session_retry_updates_existing_payment(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guest abandoning Stripe's page and retrying must update the same
    Payment row (booking_id is unique) rather than hitting the DB's unique
    constraint or leaving a stale session id behind."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    booking = await _booking_service(db_session).create_booking(_booking_payload(apartment.id))

    fake = _patch_stripe_checkout(monkeypatch)
    service = _payment_service(db_session)

    first_url = await service.create_checkout_session(booking.id)
    second_url = await service.create_checkout_session(booking.id)

    assert len(fake.calls) == 2
    assert first_url != second_url

    payment_repository = PaymentRepository(db_session)
    payment = await payment_repository.get_by_booking_id(booking.id)
    assert payment is not None
    assert payment.stripe_checkout_session_id == "cs_test_2"
    assert payment.status == PaymentStatus.PENDING


async def test_webhook_checkout_completed_confirms_booking(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    booking = await _booking_service(db_session).create_booking(_booking_payload(apartment.id))

    _patch_stripe_checkout(monkeypatch)
    service = _payment_service(db_session)
    await service.create_checkout_session(booking.id)

    event = _completed_event("cs_test_1", "pi_test_123")
    _patch_construct_event(monkeypatch, event)
    await service.handle_webhook_event(b"{}", "sig_header")

    payment = await PaymentRepository(db_session).get_by_booking_id(booking.id)
    assert payment is not None
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.stripe_payment_intent_id == "pi_test_123"

    confirmed_booking = await _booking_service(db_session).get_booking(booking.id)
    assert confirmed_booking.status == BookingStatus.CONFIRMED
    assert confirmed_booking.confirmed_at is not None


async def test_webhook_is_idempotent_on_duplicate_event(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripe delivers webhooks at-least-once, so this event WILL fire more
    than once in practice — a second delivery must be a harmless no-op."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    booking = await _booking_service(db_session).create_booking(_booking_payload(apartment.id))

    _patch_stripe_checkout(monkeypatch)
    service = _payment_service(db_session)
    await service.create_checkout_session(booking.id)

    event = _completed_event("cs_test_1", "pi_test_123")
    _patch_construct_event(monkeypatch, event)
    await service.handle_webhook_event(b"{}", "sig_header")

    booking_service = _booking_service(db_session)
    first_confirmed = await booking_service.get_booking(booking.id)

    # Second delivery of the exact same event.
    await service.handle_webhook_event(b"{}", "sig_header")

    second_confirmed = await booking_service.get_booking(booking.id)
    assert second_confirmed.status == BookingStatus.CONFIRMED
    assert second_confirmed.confirmed_at == first_confirmed.confirmed_at


async def test_webhook_invalid_signature_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_construct_event(
        monkeypatch, stripe.error.SignatureVerificationError("bad signature", "sig_header")
    )
    service = _payment_service(db_session)

    with pytest.raises(InvalidWebhookSignatureError):
        await service.handle_webhook_event(b"{}", "not-a-real-signature")


async def test_webhook_ignores_unhandled_event_types(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    await _make_rate_rule(db_session, apartment.id)
    booking = await _booking_service(db_session).create_booking(_booking_payload(apartment.id))

    event = {"type": "payment_intent.created", "data": {"object": {"id": "pi_test_999"}}}
    _patch_construct_event(monkeypatch, event)
    service = _payment_service(db_session)

    await service.handle_webhook_event(b"{}", "sig_header")

    unchanged_booking = await _booking_service(db_session).get_booking(booking.id)
    assert unchanged_booking.status == BookingStatus.PENDING
    assert await PaymentRepository(db_session).get_by_booking_id(booking.id) is None
