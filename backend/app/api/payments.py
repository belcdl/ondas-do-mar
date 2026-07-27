import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import get_payment_service
from app.schemas.payment import CheckoutSessionResponse
from app.services.payment import InvalidWebhookSignatureError, PaymentService

router = APIRouter(tags=["payments"])


@router.post(
    "/bookings/{booking_id}/checkout-session",
    response_model=CheckoutSessionResponse,
)
async def create_checkout_session(
    booking_id: uuid.UUID,
    service: PaymentService = Depends(get_payment_service),
) -> CheckoutSessionResponse:
    """Public — same reasoning as POST /bookings: guests have no accounts to
    authenticate with. 404 if the booking doesn't exist, 422 if it isn't
    payable (not PENDING, or already paid)."""
    checkout_url = await service.create_checkout_session(booking_id)
    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    service: PaymentService = Depends(get_payment_service),
) -> JSONResponse:
    """Public by necessity — Stripe calls this, not an authenticated user.
    Reads the raw request body rather than a parsed model: Stripe's signature
    is computed over the exact raw bytes, and FastAPI's JSON parsing would
    break that. Returns 400 (not 401) on a signature that doesn't verify, per
    Stripe's own convention — 200 for every other outcome, including event
    types this app doesn't act on, so Stripe doesn't keep retrying."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        await service.handle_webhook_event(payload, sig_header)
    except InvalidWebhookSignatureError as exc:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})
