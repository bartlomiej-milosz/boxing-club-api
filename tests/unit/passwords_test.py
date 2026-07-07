"""Verify password hashing, salts and accepted length boundaries."""

import pytest

from boxing_club_api.identity.passwords import hash_password, verify_password


def test_argon2id_hash_is_salted_and_verifiable() -> None:
    password = "a sample passphrase"
    digest = hash_password(password)

    assert digest.startswith("$argon2id$")
    assert hash_password(password) != digest
    assert verify_password(password, digest)
    assert not verify_password("a different passphrase", digest)


@pytest.mark.parametrize("password", ["x" * 11, "x" * 129])
def test_password_length_is_bounded(password: str) -> None:
    with pytest.raises(ValueError, match="between 12 and 128"):
        hash_password(password)
