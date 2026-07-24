from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_never_stores_plaintext() -> None:
    hashed = hash_password("Sup3rSecret!")
    assert hashed != "Sup3rSecret!"
    assert hashed.startswith("$2b$")


def test_verify_password_correct_and_incorrect() -> None:
    hashed = hash_password("Sup3rSecret!")
    assert verify_password("Sup3rSecret!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token_round_trip() -> None:
    token = create_access_token(subject="some-user-id")
    payload = decode_access_token(token)
    assert payload["sub"] == "some-user-id"


def test_decode_expired_token_raises() -> None:
    token = create_access_token(subject="some-user-id", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
