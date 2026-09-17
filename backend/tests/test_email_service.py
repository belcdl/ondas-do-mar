import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.apartment import Apartment
from app.models.booking import Booking, BookingStatus
from app.models.owner import Owner
from app.services import email as email_module
from app.services.email import EmailService


def _booking(**overrides: object) -> Booking:
    defaults: dict = dict(
        id=uuid.uuid4(),
        apartment_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        confirmation_code="ABCD1234",
        guest_full_name="Jane Guest",
        guest_email="jane@example.com",
        guest_phone=None,
        guest_count=2,
        check_in_date=date(2026, 9, 1),
        check_out_date=date(2026, 9, 4),
        status=BookingStatus.CONFIRMED,
        total_price=Decimal("300.00"),
        currency="EUR",
    )
    defaults.update(overrides)
    return Booking(**defaults)


def _apartment(**overrides: object) -> Apartment:
    defaults: dict = dict(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Casa Azul",
        address_line="Rua da Praia 12",
        city="Porto",
        country="Portugal",
        check_in_instructions="El código de la puerta es 4321.",
    )
    defaults.update(overrides)
    return Apartment(**defaults)


def _owner(**overrides: object) -> Owner:
    defaults: dict = dict(
        id=uuid.uuid4(), full_name="Owner Name", email="owner@example.com", phone="+34600000000"
    )
    defaults.update(overrides)
    return Owner(**defaults)


async def test_send_booking_confirmation_renders_with_correct_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    async def fake_send_message(message, template_name) -> None:
        calls.append((message, template_name))

    monkeypatch.setattr(email_module, "send_message", fake_send_message)

    booking = _booking()
    apartment = _apartment()
    owner = _owner()

    await EmailService().send_booking_confirmation(booking, apartment, owner)

    assert len(calls) == 1
    message, template_name = calls[0]
    assert template_name == "booking_confirmation.html"
    assert message.recipients[0].email == booking.guest_email
    assert message.bcc[0].email == owner.email
    assert message.reply_to[0].email == "no-reply@ondasdomar.com"
    assert message.template_body["booking"]["confirmation_code"] == booking.confirmation_code
    assert message.template_body["booking"]["check_in_date"] == "2026-09-01"
    assert message.template_body["apartment"]["name"] == apartment.name
    assert (
        message.template_body["apartment"]["check_in_instructions"]
        == apartment.check_in_instructions
    )
    assert message.template_body["owner"]["full_name"] == owner.full_name
    assert message.template_body["owner"]["phone"] == owner.phone


async def test_send_checkin_reminder_renders_with_correct_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    async def fake_send_message(message, template_name) -> None:
        calls.append((message, template_name))

    monkeypatch.setattr(email_module, "send_message", fake_send_message)

    booking = _booking()
    apartment = _apartment()
    owner = _owner()

    await EmailService().send_checkin_reminder(booking, apartment, owner)

    assert len(calls) == 1
    message, template_name = calls[0]
    assert template_name == "checkin_reminder.html"
    assert message.recipients[0].email == booking.guest_email
    assert message.bcc[0].email == owner.email
    assert message.reply_to[0].email == "no-reply@ondasdomar.com"
    assert message.template_body["booking"]["confirmation_code"] == booking.confirmation_code
    assert message.template_body["owner"]["full_name"] == owner.full_name


async def test_send_booking_confirmation_swallows_send_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing_send_message(message, template_name) -> None:
        raise RuntimeError("smtp connection refused")

    monkeypatch.setattr(email_module, "send_message", failing_send_message)

    booking = _booking()
    apartment = _apartment()
    owner = _owner()

    with caplog.at_level(logging.WARNING):
        # Must not raise — a broken SMTP connection can never bubble up into
        # the Stripe webhook / scheduler flow that triggered this.
        await EmailService().send_booking_confirmation(booking, apartment, owner)

    assert "smtp connection refused" in caplog.text
    assert str(booking.id) in caplog.text


async def test_send_checkin_reminder_swallows_send_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing_send_message(message, template_name) -> None:
        raise RuntimeError("smtp connection refused")

    monkeypatch.setattr(email_module, "send_message", failing_send_message)

    booking = _booking()
    apartment = _apartment()
    owner = _owner()

    with caplog.at_level(logging.WARNING):
        await EmailService().send_checkin_reminder(booking, apartment, owner)  # must not raise

    assert "smtp connection refused" in caplog.text
