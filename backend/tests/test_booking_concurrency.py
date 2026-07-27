"""Real-concurrency verification of the ex_bookings_no_overlap_confirmed
EXCLUDE constraint (Decision 027).

This cannot use the conftest db_session/client fixtures: those wrap a single
connection in a savepoint-based outer transaction, which is inherently
sequential and can't represent two genuinely concurrent transactions. To
prove the constraint holds under real concurrency, this test opens two
independent sessions/connections against the actual dev database, commits
for real, and cleans up explicitly afterwards.
"""

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.core.exceptions import ConflictError
from app.db.session import async_session_factory
from app.models.apartment import Apartment
from app.models.booking import Booking
from app.models.owner import Owner
from app.repositories.apartment import ApartmentRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.booking import BookingCreate
from app.schemas.owner import OwnerCreate
from app.schemas.rate_rule import RateRuleCreate
from app.services.apartment import ApartmentService
from app.services.booking import BookingService
from app.services.owner import OwnerService
from app.services.rate_rule import RateRuleService


async def _confirm(booking_id: uuid.UUID) -> str:
    async with async_session_factory() as session:
        service = BookingService(
            BookingRepository(session),
            ApartmentRepository(session),
            OwnerRepository(session),
            RateRuleService(RateRuleRepository(session), BookingRepository(session)),
        )
        try:
            await service.confirm_booking(booking_id)
            return "confirmed"
        except ConflictError:
            return "conflict"


async def test_exclude_constraint_rejects_concurrent_overlapping_confirmations() -> None:
    async with async_session_factory() as setup_session:
        owner_service = OwnerService(
            OwnerRepository(setup_session),
            OwnerInvitationRepository(setup_session),
            UserRepository(setup_session),
        )
        owner = await owner_service.create_owner(
            OwnerCreate(
                full_name="Concurrency Owner",
                email=f"concurrency-{uuid.uuid4()}@example.com",
                phone=None,
            )
        )
        apartment = await ApartmentService(
            ApartmentRepository(setup_session), OwnerRepository(setup_session)
        ).create_apartment(
            ApartmentCreate(
                owner_id=owner.id,
                name="Concurrency Apt",
                address_line="Street 1",
                city="Porto",
                country="Portugal",
            )
        )

        check_in = date.today() + timedelta(days=300)
        check_out = check_in + timedelta(days=5)
        await RateRuleService(
            RateRuleRepository(setup_session), BookingRepository(setup_session)
        ).create_rate_rule(
            RateRuleCreate(
                apartment_id=apartment.id,
                start_date=check_in,
                end_date=check_out + timedelta(days=2),
                price_per_night=Decimal("100.00"),
                min_stay=1,
            )
        )
        booking_service = BookingService(
            BookingRepository(setup_session),
            ApartmentRepository(setup_session),
            OwnerRepository(setup_session),
            RateRuleService(RateRuleRepository(setup_session), BookingRepository(setup_session)),
        )
        booking_a = await booking_service.create_booking(
            BookingCreate(
                apartment_id=apartment.id,
                guest_full_name="Guest A",
                guest_email="a@example.com",
                guest_count=2,
                check_in_date=check_in,
                check_out_date=check_out,
            )
        )
        booking_b = await booking_service.create_booking(
            BookingCreate(
                apartment_id=apartment.id,
                guest_full_name="Guest B",
                guest_email="b@example.com",
                guest_count=2,
                check_in_date=check_in + timedelta(days=2),
                check_out_date=check_out + timedelta(days=2),
            )
        )

    try:
        results = await asyncio.gather(_confirm(booking_a.id), _confirm(booking_b.id))
        assert sorted(results) == ["confirmed", "conflict"]
    finally:
        async with async_session_factory() as cleanup_session:
            await cleanup_session.execute(
                delete(Booking).where(Booking.apartment_id == apartment.id)
            )
            await cleanup_session.execute(delete(Apartment).where(Apartment.id == apartment.id))
            await cleanup_session.execute(delete(Owner).where(Owner.id == owner.id))
            await cleanup_session.commit()
