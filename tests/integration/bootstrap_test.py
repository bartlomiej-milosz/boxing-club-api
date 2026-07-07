"""Verify initial-owner bootstrap safety, normalization and concurrent execution."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.bootstrap import OwnerBootstrapConflict, bootstrap_owner
from boxing_club_api.identity.models import AppUser, UserRole
from boxing_club_api.identity.passwords import verify_password

pytestmark = pytest.mark.integration


def test_bootstrap_normalizes_owner_and_never_resets_password(sessions: SessionFactory) -> None:
    bootstrap_owner(
        sessions,
        email="  OWNER@example.test ",
        first_name=" Sample ",
        last_name="Owner",
        password="original passphrase",
    )

    for email in ("owner@example.test", "other@example.test"):
        with pytest.raises(OwnerBootstrapConflict, match="already exists"):
            bootstrap_owner(
                sessions,
                email=email,
                first_name="Other",
                last_name="Owner",
                password="replacement passphrase",
            )

    with sessions() as session:
        user = session.scalars(select(AppUser)).one()
        role = session.scalars(select(UserRole)).one()
        assert (user.email, user.first_name, user.status) == (
            "owner@example.test",
            "Sample",
            "ACTIVE",
        )
        assert (role.user_id, role.role) == (user.id, "OWNER")
        assert verify_password("original passphrase", user.password_hash)
        assert not verify_password("replacement passphrase", user.password_hash)


def test_simultaneous_bootstraps_can_create_only_one_owner(sessions: SessionFactory) -> None:
    start = Barrier(2, timeout=5)

    def try_bootstrap(email: str) -> bool:
        start.wait()
        try:
            bootstrap_owner(
                sessions,
                email=email,
                first_name="Sample",
                last_name="Owner",
                password="a sample passphrase",
            )
        except OwnerBootstrapConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(try_bootstrap, "first@example.test")
        second = executor.submit(try_bootstrap, "second@example.test")
        results = [first.result(timeout=10), second.result(timeout=10)]

    assert sorted(results) == [False, True]
    with sessions() as session:
        assert session.scalars(select(UserRole.role)).one() == "OWNER"
        assert session.scalars(select(AppUser.id)).one()
