"""Verify fictional seeding is atomic, opt-in and refuses existing accounts."""

import pytest
from sqlalchemy import func, select
from tests.support import NOW

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.demo import seed_demo
from boxing_club_api.identity.models import AppUser
from boxing_club_api.identity.passwords import verify_password
from boxing_club_api.scheduling.models import TrainingSession

pytestmark = pytest.mark.integration


def test_demo_seeds_fictional_data_once_without_resetting_credentials(
    sessions: SessionFactory,
) -> None:
    result = seed_demo(sessions, "a local demo passphrase", clock=lambda: NOW)
    assert result.owner_email == "owner@example.test"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 4
        assert session.get_one(TrainingSession, result.session_id).starts_at > NOW
    with pytest.raises(ApplicationError, match="empty database"):
        seed_demo(sessions, "replacement passphrase", clock=lambda: NOW)
    with sessions() as session:
        owner = session.scalars(select(AppUser).where(AppUser.email == result.owner_email)).one()
        assert verify_password("a local demo passphrase", owner.password_hash)
        assert not verify_password("replacement passphrase", owner.password_hash)
