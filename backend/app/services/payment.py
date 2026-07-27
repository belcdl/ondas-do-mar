import logging
import uuid

import stripe

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, BusinessRuleError, NotFoundError
from app.models.booking import BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.repositories.apartment import ApartmentRepository
from app.repositories.payment import PaymentRepository
from app.services.booking import BookingService

logger = logging.getLogger(__name__)


class PaymentNotFoundError(NotFoundError):
    """Raised when no payment exists for the given booking."""


class BookingNotPayableError(BusinessRuleError):
    """Raised when a checkout session is requested for a booking that isn't PENDING."""


class InvalidWebhookSignatureError(AuthenticationError):
    """Raised when a Stripe webhook payload's signature can't be verified."""


class PaymentService:
    """Business rules for Payment/Stripe Checkout. Delegates persistence to
    PaymentRepository and reuses BookingService for the PENDING->CONFIRMED
    transition once a payment succeeds."""

    def __init__(
        self,
        repository: PaymentRepository,
        apartment_repository: ApartmentRepository,
        booking_service: BookingService,
    ) -> None:
        self.repository = repository
        self.apartment_repository = apartment_repository
        self.booking_service = booking_service

    async def create_checkout_session(self, booking_id: uuid.UUID) -> str:
        booking = await self.booking_service.get_booking(booking_id)
        # booking.apartment_id is a FK with ondelete=RESTRICT, so the
        # apartment is guaranteed to still exist while the booking does.
        apartment = await self.apartment_repository.get_by_id(booking.apartment_id)

        if booking.status != BookingStatus.PENDING:
            raise BookingNotPayableError(
                f"Cannot pay for a booking with status '{booking.status.value}'"
            )

        existing_payment = await self.repository.get_by_booking_id(booking.id)
        if existing_payment is not None and existing_payment.status == PaymentStatus.SUCCEEDED:
            raise BookingNotPayableError("This booking has already been paid for")

        settings = get_settings()
        stripe.api_key = settings.stripe_secret_key
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": booking.currency.lower(),
                        "unit_amount": int(booking.total_price * 100),
                        "product_data": {
                            "name": (
                                f"{apartment.name} — {booking.check_in_date.isoformat()} "
                                f"to {booking.check_out_date.isoformat()}"
                            ),
                        },
                    },
                    "quantity": 1,
                }
            ],
            success_url=(
                f"{settings.frontend_base_url}/booking-confirmed"
                f"?confirmation_code={booking.confirmation_code}"
            ),
            cancel_url=f"{settings.frontend_base_url}/booking-cancelled",
            metadata={"booking_id": str(booking.id)},
        )

        if existing_payment is not None:
            existing_payment.stripe_checkout_session_id = session.id
            existing_payment.status = PaymentStatus.PENDING
            existing_payment.amount = booking.total_price
            existing_payment.currency = booking.currency
            await self.repository.update(existing_payment)
        else:
            payment = Payment(
                booking_id=booking.id,
                stripe_checkout_session_id=session.id,
                amount=booking.total_price,
                currency=booking.currency,
                status=PaymentStatus.PENDING,
            )
            await self.repository.create(payment)

        return session.url

    async def handle_webhook_event(self, payload: bytes, sig_header: str) -> None:
        settings = get_settings()
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except stripe.error.SignatureVerificationError as exc:
            raise InvalidWebhookSignatureError("Invalid Stripe webhook signature") from exc

        if event["type"] != "checkout.session.completed":
            return

        session = event["data"]["object"]
        checkout_session_id = session["id"]

        payment = await self.repository.get_by_checkout_session_id(checkout_session_id)
        if payment is None:
            logger.warning(
                "Received checkout.session.completed for unknown session %s", checkout_session_id
            )
            return

        if payment.status == PaymentStatus.SUCCEEDED:
            return

        payment.status = PaymentStatus.SUCCEEDED
        payment.stripe_payment_intent_id = session["payment_intent"]
        await self.repository.update(payment)

        await self.booking_service.confirm_booking(payment.booking_id)
