import logging
from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.core.config import get_settings
from app.models.apartment import Apartment
from app.models.booking import Booking
from app.models.owner import Owner

logger = logging.getLogger(__name__)

_TEMPLATE_FOLDER = Path(__file__).resolve().parent.parent / "templates" / "emails"


def _connection_config() -> ConnectionConfig:
    settings = get_settings()
    return ConnectionConfig(
        MAIL_USERNAME=settings.smtp_username or "",
        MAIL_PASSWORD=settings.smtp_password or "",
        MAIL_PORT=settings.smtp_port,
        MAIL_SERVER=settings.smtp_host or "",
        MAIL_STARTTLS=settings.smtp_use_tls,
        MAIL_SSL_TLS=False,
        MAIL_FROM=settings.smtp_from_email,
        MAIL_FROM_NAME=settings.smtp_from_name,
        USE_CREDENTIALS=bool(settings.smtp_username),
        TEMPLATE_FOLDER=_TEMPLATE_FOLDER,
        # No SMTP host configured (local dev without a mail account, or the
        # test suite) — suppress the actual network send rather than let it
        # hang for MAIL_TIMEOUT (60s default) trying to connect to "".
        # Template rendering still runs, so send_booking_confirmation's
        # caller-visible behavior is unaffected either way.
        SUPPRESS_SEND=0 if settings.smtp_host else 1,
    )


async def send_message(message: MessageSchema, template_name: str) -> None:
    """Separated out so tests can monkeypatch it instead of hitting a real
    SMTP server — same pattern as app.services.ical_sync.fetch_ical."""
    fastmail = FastMail(_connection_config())
    await fastmail.send_message(message, template_name=template_name)


def _booking_context(booking: Booking) -> dict:
    return {
        "guest_full_name": booking.guest_full_name,
        "confirmation_code": booking.confirmation_code,
        "check_in_date": booking.check_in_date.isoformat(),
        "check_out_date": booking.check_out_date.isoformat(),
        "guest_count": booking.guest_count,
        "total_price": booking.total_price,
        "currency": booking.currency,
    }


def _apartment_context(apartment: Apartment) -> dict:
    return {
        "name": apartment.name,
        "address_line": apartment.address_line,
        "city": apartment.city,
        # Only ever reaches a guest through this template — never through
        # ApartmentPublicRead (app/schemas/apartment.py).
        "check_in_instructions": apartment.check_in_instructions,
    }


def _owner_context(owner: Owner) -> dict:
    return {"full_name": owner.full_name, "phone": owner.phone}


class EmailService:
    """Sends guest-facing transactional emails (booking confirmation,
    check-in reminder). Sender and Reply-To are always the shared inbox
    (Settings.smtp_from_email/smtp_from_name), never the owner's own email —
    the owner is BCC'd only so they have a record, not as the primary
    contact. Never raises: a send failure is logged and swallowed so it can
    never break the flow that triggered it (the Stripe webhook or the
    scheduler's daily tick) — same resilience pattern as
    ApartmentPhotoService.upload_photo's WebP-conversion fallback.

    Templates (app/templates/emails/) are Spanish-only for now, no i18n —
    revisit once the guest-facing frontend grows a second locale worth
    mirroring in email."""

    async def send_booking_confirmation(
        self, booking: Booking, apartment: Apartment, owner: Owner
    ) -> None:
        message = MessageSchema(
            subject=f"Confirmación de tu reserva — {apartment.name}",
            recipients=[booking.guest_email],
            bcc=[owner.email],
            reply_to=[get_settings().smtp_from_email],
            subtype=MessageType.html,
            template_body={
                "booking": _booking_context(booking),
                "apartment": _apartment_context(apartment),
                "owner": _owner_context(owner),
            },
        )
        try:
            await send_message(message, "booking_confirmation.html")
        except Exception as exc:
            logger.warning(
                "Could not send booking confirmation email for booking %s: %s",
                booking.id,
                exc,
            )

    async def send_checkin_reminder(
        self, booking: Booking, apartment: Apartment, owner: Owner
    ) -> None:
        message = MessageSchema(
            subject=f"Tu llegada es mañana — {apartment.name}",
            recipients=[booking.guest_email],
            bcc=[owner.email],
            reply_to=[get_settings().smtp_from_email],
            subtype=MessageType.html,
            template_body={
                "booking": _booking_context(booking),
                "apartment": _apartment_context(apartment),
                "owner": _owner_context(owner),
            },
        )
        try:
            await send_message(message, "checkin_reminder.html")
        except Exception as exc:
            logger.warning(
                "Could not send check-in reminder email for booking %s: %s",
                booking.id,
                exc,
            )
