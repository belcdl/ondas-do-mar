"""Cross-cutting authorization tests (Sprint 6.2).

Covers: owner accessing own vs. other owners' Apartments/Bookings/profile,
admin having full access, unauthenticated (401) vs authenticated-but-
forbidden (403). Uses db_session directly (alongside client/admin_headers)
because linking a User to an Owner has no public endpoint yet — tests set
owner.user_id directly on the ORM object, the same pattern already used by
test_owner_apartment_relationship.py for constraint testing.
"""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from app.repositories.owner import OwnerRepository
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService
from tests.conftest import auth_headers_for


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
    client: AsyncClient, headers: dict[str, str], owner_id: str, **overrides: str
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
    # Every apartment in this file needs pricing before it can be booked, so
    # set up a wide covering rate rule here rather than in every test.
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


async def _make_owner_with_linked_user(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    **overrides: str,
) -> tuple[dict, dict[str, str]]:
    """Creates an Owner (via admin) and an owner-role User, links them
    directly at the ORM level, and returns (owner_dict, that user's auth headers)."""
    owner = await _create_owner(client, admin_headers, **overrides)
    user = await UserService(UserRepository(db_session)).create_user(
        UserCreate(
            email=f"owner-user-{uuid.uuid4()}@example.com",
            password="Sup3rSecret!",
            full_name="Owner User",
            role=UserRole.OWNER,
        )
    )
    owner_repo = OwnerRepository(db_session)
    owner_obj = await owner_repo.get_by_id(uuid.UUID(owner["id"]))
    assert owner_obj is not None
    owner_obj.user_id = user.id
    db_session.add(owner_obj)
    await db_session.commit()
    return owner, auth_headers_for(user)


# --- Apartment: owner accessing their own vs. someone else's -----------------------


async def test_owner_can_access_own_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    response = await client.get(f"/apartments/{apartment['id']}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["id"] == apartment["id"]


async def test_owner_cannot_access_other_owners_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])

    response = await client.get(f"/apartments/{apartment_b['id']}", headers=headers_a)
    assert response.status_code == 403


async def test_owner_apartment_list_scoped_to_own(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_a = await _create_apartment(client, admin_headers, owner_a["id"])
    await _create_apartment(client, admin_headers, owner_b["id"])

    response = await client.get("/apartments", headers=headers_a)
    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert ids == [apartment_a["id"]]


async def test_owner_can_update_own_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    response = await client.patch(
        f"/apartments/{apartment['id']}", json={"bedrooms": 2}, headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["bedrooms"] == 2


async def test_owner_cannot_update_other_owners_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])

    response = await client.patch(
        f"/apartments/{apartment_b['id']}", json={"bedrooms": 2}, headers=headers_a
    )
    assert response.status_code == 403


async def test_owner_cannot_create_apartment_for_another_owner(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    _owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)

    response = await client.post(
        "/apartments",
        json={
            "owner_id": owner_b["id"],
            "name": "Stolen",
            "address_line": "Street 1",
            "city": "Porto",
            "country": "Portugal",
        },
        headers=headers_a,
    )
    assert response.status_code == 403


async def test_owner_cannot_deactivate_other_owners_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])

    response = await client.post(
        f"/apartments/{apartment_b['id']}/deactivate", headers=headers_a
    )
    assert response.status_code == 403


async def test_owner_cannot_reassign_own_apartment_to_another_owner(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_a = await _create_apartment(client, admin_headers, owner_a["id"])

    response = await client.patch(
        f"/apartments/{apartment_a['id']}", json={"owner_id": owner_b["id"]}, headers=headers_a
    )
    assert response.status_code == 403


# --- Booking: owner accessing their own vs. someone else's -------------------------


async def test_owner_can_access_own_booking(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.get(f"/bookings/{booking['id']}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["id"] == booking["id"]


async def test_owner_cannot_access_other_owners_booking(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])
    booking_b = await _create_booking(client, apartment_b["id"])

    response = await client.get(f"/bookings/{booking_b['id']}", headers=headers_a)
    assert response.status_code == 403


async def test_owner_booking_list_scoped_to_own(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_a = await _create_apartment(client, admin_headers, owner_a["id"])
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])
    booking_a = await _create_booking(client, apartment_a["id"])
    await _create_booking(client, apartment_b["id"])

    response = await client.get("/bookings", headers=headers_a)
    assert response.status_code == 200
    ids = [b["id"] for b in response.json()]
    assert ids == [booking_a["id"]]


async def test_owner_supplied_owner_id_filter_is_overridden_not_trusted(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """A non-admin passing ?owner_id=<someone else> must still only see their
    own bookings — the filter is force-scoped, not merely validated."""
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_a = await _create_apartment(client, admin_headers, owner_a["id"])
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])
    booking_a = await _create_booking(client, apartment_a["id"])
    await _create_booking(client, apartment_b["id"])

    response = await client.get(
        "/bookings", params={"owner_id": owner_b["id"]}, headers=headers_a
    )
    assert response.status_code == 200
    ids = [b["id"] for b in response.json()]
    assert ids == [booking_a["id"]]


async def test_owner_cannot_confirm_other_owners_booking(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])
    booking_b = await _create_booking(client, apartment_b["id"])

    response = await client.post(f"/bookings/{booking_b['id']}/confirm", headers=headers_a)
    assert response.status_code == 403


async def test_owner_cannot_set_own_booking_total_price(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """total_price is server-computed and admin-only to override — even the
    owner of the booking's apartment may not set it, same rule as apartments'
    owner_id reassignment."""
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.patch(
        f"/bookings/{booking['id']}", json={"total_price": "1.00"}, headers=owner_headers
    )
    assert response.status_code == 403


async def test_admin_can_set_booking_total_price(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])

    response = await client.patch(
        f"/bookings/{booking['id']}", json={"total_price": "500.00"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["total_price"] == "500.00"


# --- Owner profile: self-access vs. others ------------------------------------------


async def test_owner_can_view_and_update_own_profile(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)

    get_response = await client.get(f"/owners/{owner['id']}", headers=owner_headers)
    assert get_response.status_code == 200

    patch_response = await client.patch(
        f"/owners/{owner['id']}", json={"phone": "+34600999888"}, headers=owner_headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["phone"] == "+34600999888"


async def test_owner_cannot_view_another_owners_profile(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    _owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)

    response = await client.get(f"/owners/{owner_b['id']}", headers=headers_a)
    assert response.status_code == 403


async def test_owner_cannot_relink_own_user_id(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)

    response = await client.patch(
        f"/owners/{owner['id']}", json={"user_id": str(uuid.uuid4())}, headers=owner_headers
    )
    assert response.status_code == 403


# --- Admin: full access -------------------------------------------------------------


async def test_admin_can_access_any_owner_profile(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    response = await client.get(f"/owners/{owner['id']}", headers=admin_headers)
    assert response.status_code == 200


async def test_admin_can_access_any_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    response = await client.get(f"/apartments/{apartment['id']}", headers=admin_headers)
    assert response.status_code == 200


async def test_admin_can_access_any_booking(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner, _headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    booking = await _create_booking(client, apartment["id"])
    response = await client.get(f"/bookings/{booking['id']}", headers=admin_headers)
    assert response.status_code == 200


async def test_admin_can_list_all_bookings_across_owners(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    owner_a, _ = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _ = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_a = await _create_apartment(client, admin_headers, owner_a["id"])
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])
    booking_a = await _create_booking(client, apartment_a["id"])
    booking_b = await _create_booking(client, apartment_b["id"])

    response = await client.get("/bookings", headers=admin_headers)
    ids = {b["id"] for b in response.json()}
    assert {booking_a["id"], booking_b["id"]}.issubset(ids)


# --- Generic 401 vs 403 --------------------------------------------------------------


async def test_unauthenticated_request_returns_401(client: AsyncClient) -> None:
    response = await client.get(f"/apartments/{uuid.uuid4()}")
    assert response.status_code == 401


async def test_authenticated_owner_without_permission_returns_403_not_404(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """The resource genuinely exists but isn't the caller's — must be 403,
    never 404 (a 404 here would be using non-existence to hide a real resource)."""
    owner_a, headers_a = await _make_owner_with_linked_user(client, db_session, admin_headers)
    owner_b, _headers_b = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment_b = await _create_apartment(client, admin_headers, owner_b["id"])

    response = await client.get(f"/apartments/{apartment_b['id']}", headers=headers_a)
    assert response.status_code == 403
    assert response.status_code != 404


async def test_genuinely_missing_resource_still_returns_404(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """Contrast with the above: a resource that truly doesn't exist is still
    a real 404, not disguised as 403 either."""
    _owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    response = await client.get(f"/apartments/{uuid.uuid4()}", headers=owner_headers)
    assert response.status_code == 404
