"""Full HTTP flow for the owner invitation feature: admin invites an owner
with no login yet, the invitation link's token is redeemed via
POST /auth/accept-invitation, and the resulting access token is scoped the
same way as any other owner login (see test_authorization.py)."""

import uuid
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient


async def _create_owner(client: AsyncClient, headers: dict[str, str], **overrides: str) -> dict:
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": "+34600000000",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/owners", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


def _extract_token(invitation_link: str) -> str:
    query = parse_qs(urlparse(invitation_link).query)
    return query["token"][0]


async def test_invite_owner_requires_admin(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)

    response = await client.post(f"/api/v1/owners/{owner['id']}/invite")
    assert response.status_code == 401


async def test_invite_owner_not_found_returns_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(f"/api/v1/owners/{uuid.uuid4()}/invite", headers=admin_headers)
    assert response.status_code == 404


async def test_invite_already_onboarded_owner_returns_409(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    invite_response = await client.post(f"/api/v1/owners/{owner['id']}/invite", headers=admin_headers)
    token = _extract_token(invite_response.json()["invitation_link"])
    accept_response = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "password": "Sup3rSecret!", "full_name": "Real Name"},
    )
    assert accept_response.status_code == 200

    response = await client.post(f"/api/v1/owners/{owner['id']}/invite", headers=admin_headers)
    assert response.status_code == 409


async def test_accept_invitation_unknown_token_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": "not-a-real-token", "password": "Sup3rSecret!", "full_name": "Nobody"},
    )
    assert response.status_code == 404


async def test_accept_invitation_already_used_returns_409(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner = await _create_owner(client, admin_headers)
    invite_response = await client.post(f"/api/v1/owners/{owner['id']}/invite", headers=admin_headers)
    token = _extract_token(invite_response.json()["invitation_link"])

    first = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "password": "Sup3rSecret!", "full_name": "Real Name"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "password": "AnotherPassword!", "full_name": "Real Name"},
    )
    assert second.status_code == 409


async def test_full_invitation_flow_scopes_owner_correctly(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    owner_a = await _create_owner(client, admin_headers)
    owner_b = await _create_owner(client, admin_headers)

    invite_response = await client.post(f"/api/v1/owners/{owner_a['id']}/invite", headers=admin_headers)
    assert invite_response.status_code == 200
    invitation = invite_response.json()
    token = _extract_token(invitation["invitation_link"])

    accept_response = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "password": "Sup3rSecret!", "full_name": "Real Owner Name"},
    )
    assert accept_response.status_code == 200
    owner_headers = {"Authorization": f"Bearer {accept_response.json()['access_token']}"}

    own_profile = await client.get(f"/api/v1/owners/{owner_a['id']}", headers=owner_headers)
    assert own_profile.status_code == 200
    assert own_profile.json()["id"] == owner_a["id"]

    other_profile = await client.get(f"/api/v1/owners/{owner_b['id']}", headers=owner_headers)
    assert other_profile.status_code == 403

    me_response = await client.get("/api/v1/auth/me", headers=owner_headers)
    assert me_response.status_code == 200
    assert me_response.json()["full_name"] == "Real Owner Name"
