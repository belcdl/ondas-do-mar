import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_authorized_booking,
    get_booking_service,
    get_current_active_user,
    get_current_owner_or_none,
)
from app.core.exceptions import PermissionDeniedError
from app.models.booking import Booking, BookingStatus
from app.models.owner import Owner
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate, BookingRead, BookingUpdate
from app.services.booking import BookingService

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    data: BookingCreate, service: BookingService = Depends(get_booking_service)
) -> Booking:
    """Public — guests have no accounts (Decision 001-era design, Sprint 5.1).
    404 if the apartment doesn't exist, 422 if its owner is inactive or dates are invalid."""
    return await service.create_booking(data)


@router.get("", response_model=list[BookingRead])
async def list_bookings(
    apartment_id: uuid.UUID | None = Query(None, description="Filter by apartment."),
    owner_id: uuid.UUID | None = Query(
        None, description="Filter by owner. Ignored for non-admins — forced to their own."
    ),
    booking_status: BookingStatus | None = Query(
        None, alias="status", description="Filter by status."
    ),
    check_in_from: date | None = Query(None, description="Only bookings checking in on/after this date."),
    check_in_to: date | None = Query(None, description="Only bookings checking in on/before this date."),
    guest_email: str | None = Query(None, description="Filter by guest email (case-insensitive)."),
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: BookingService = Depends(get_booking_service),
) -> list[Booking]:
    """List bookings — management view, requires authentication. An admin
    sees everything and may filter by any owner_id; an owner-role caller is
    always scoped to their own bookings regardless of the owner_id supplied."""
    effective_owner_id = owner_id
    if current_user.role != UserRole.ADMIN:
        if caller_owner is None:
            return []
        effective_owner_id = caller_owner.id

    return await service.list_bookings(
        apartment_id=apartment_id,
        owner_id=effective_owner_id,
        booking_status=booking_status,
        check_in_from=check_in_from,
        check_in_to=check_in_to,
        guest_email=guest_email,
    )


@router.get("/by-confirmation/{confirmation_code}", response_model=BookingRead)
async def get_booking_by_confirmation_code(
    confirmation_code: str, service: BookingService = Depends(get_booking_service)
) -> Booking:
    """Public — the confirmation code is the guest's own credential to look up
    their booking without an account. Returns 404 if not found."""
    return await service.get_booking_by_confirmation_code(confirmation_code)


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(booking: Booking = Depends(get_authorized_booking)) -> Booking:
    """Fetch a single booking. 404 if it doesn't exist, 403 if it exists but isn't the caller's."""
    return booking


@router.patch("/{booking_id}", response_model=BookingRead)
async def update_booking(
    data: BookingUpdate,
    current_user: User = Depends(get_current_active_user),
    booking: Booking = Depends(get_authorized_booking),
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Partially update guest/date/price details. Status changes go through
    confirm/cancel/complete, not PATCH. Setting total_price is admin-only —
    an admin manually correcting a price after the fact is a legitimate
    override, an owner is not allowed to adjust their own booking's price."""
    if "total_price" in data.model_fields_set and current_user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Only an admin can adjust a booking's total price")
    return await service.update_booking(booking.id, data)


@router.post("/{booking_id}/confirm", response_model=BookingRead)
async def confirm_booking(
    booking: Booking = Depends(get_authorized_booking),
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Confirm a pending booking. Returns 422 if it's already cancelled or completed."""
    return await service.confirm_booking(booking.id)


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking: Booking = Depends(get_authorized_booking),
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Cancel a booking. Returns 422 if it's already completed."""
    return await service.cancel_booking(booking.id)


@router.post("/{booking_id}/complete", response_model=BookingRead)
async def complete_booking(
    booking: Booking = Depends(get_authorized_booking),
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Mark a confirmed booking as completed. Returns 422 if it was never confirmed or was cancelled."""
    return await service.complete_booking(booking.id)
