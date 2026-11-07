"""Read trainer catalog data and serialize owner updates against session creation."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, text

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.core.pagination import page_offset
from boxing_club_api.db.session import SessionFactory

from .authentication import Principal, require_owner
from .models import AppUser, TrainerProfile


@dataclass(frozen=True)
class Trainer:
    """Trainer catalog identity and biography, excluding account contact and credentials."""

    id: UUID
    first_name: str
    last_name: str
    bio: str | None
    active: bool


def list_trainers(
    sessions: SessionFactory,
    principal: Principal,
    *,
    page: int,
    size: int,
    include_inactive: bool = False,
) -> tuple[list[Trainer], int]:
    """Page trainers by surname, first name and ID; only owners may include inactive profiles."""
    offset = page_offset(page, size)
    if include_inactive:
        require_owner(principal)
    statement = (
        select(
            AppUser.id,
            AppUser.first_name,
            AppUser.last_name,
            TrainerProfile.bio,
            TrainerProfile.active,
        )
        .join(TrainerProfile, TrainerProfile.user_id == AppUser.id)
        .where(AppUser.status == "ACTIVE")
    )
    if not include_inactive:
        statement = statement.where(TrainerProfile.active.is_(True))
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = session.execute(
            statement.order_by(AppUser.last_name, AppUser.first_name, AppUser.id)
            .offset(offset)
            .limit(size)
        ).all()
        return [Trainer(*row) for row in rows], total


def update_trainer(
    sessions: SessionFactory,
    principal: Principal,
    trainer_id: UUID,
    *,
    changes: dict[str, str | bool | None],
) -> Trainer:
    """Update biography or active state under the trainer row lock, preserving existing sessions."""
    require_owner(principal)
    with sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        trainer = session.scalar(
            select(TrainerProfile).where(TrainerProfile.user_id == trainer_id).with_for_update()
        )
        if trainer is None:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Trainer not found.")
        user = session.get_one(AppUser, trainer_id)
        if "bio" in changes:
            bio = changes["bio"]
            assert bio is None or isinstance(bio, str)
            trainer.bio = bio
        if "active" in changes:
            active = changes["active"]
            assert isinstance(active, bool)
            trainer.active = active
        result = Trainer(user.id, user.first_name, user.last_name, trainer.bio, trainer.active)
    return result
