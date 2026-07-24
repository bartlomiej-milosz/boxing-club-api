"""Create dated sessions with room and trainer overlap protection."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Install btree_gist and create session constraints, audit fields and schedule indexes.

    Exclude overlapping SCHEDULED half-open ranges for each room and trainer.
    Leave cross-table capacity and catalog-activity checks to the locked creation service.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        CREATE TABLE public.training_session (
            id uuid NOT NULL,
            title varchar(120) NOT NULL,
            trainer_id uuid NOT NULL,
            room_id uuid NOT NULL,
            starts_at timestamptz NOT NULL,
            ends_at timestamptz NOT NULL,
            booking_closes_at timestamptz NOT NULL,
            capacity integer NOT NULL,
            status varchar(9) NOT NULL,
            created_at timestamptz NOT NULL,
            cancelled_at timestamptz,
            cancelled_by_user_id uuid,
            cancellation_reason varchar(1000),
            CONSTRAINT pk_training_session PRIMARY KEY (id),
            CONSTRAINT fk_training_session_trainer
                FOREIGN KEY (trainer_id) REFERENCES public.trainer_profile (user_id),
            CONSTRAINT fk_training_session_room
                FOREIGN KEY (room_id) REFERENCES public.room (id),
            CONSTRAINT fk_training_session_cancelled_by
                FOREIGN KEY (cancelled_by_user_id) REFERENCES public.app_user (id),
            CONSTRAINT ck_training_session_title_trimmed
                CHECK (title <> '' AND title !~ '^[[:space:]]|[[:space:]]$'),
            CONSTRAINT ck_training_session_time_range CHECK (ends_at > starts_at),
            CONSTRAINT ck_training_session_booking_cutoff
                CHECK (booking_closes_at <= starts_at),
            CONSTRAINT ck_training_session_capacity_positive CHECK (capacity > 0),
            CONSTRAINT ck_training_session_status
                CHECK (status IN ('SCHEDULED', 'CANCELLED')),
            CONSTRAINT ck_training_session_cancellation_audit CHECK (
                (status = 'SCHEDULED' AND cancelled_at IS NULL
                    AND cancelled_by_user_id IS NULL AND cancellation_reason IS NULL)
                OR
                (status = 'CANCELLED' AND cancelled_at IS NOT NULL
                    AND cancelled_by_user_id IS NOT NULL AND cancellation_reason IS NOT NULL
                    AND cancellation_reason <> ''
                    AND cancellation_reason !~ '^[[:space:]]|[[:space:]]$')
            ),
            CONSTRAINT ex_training_session_room_time EXCLUDE USING gist (
                room_id WITH =,
                tstzrange(starts_at, ends_at, '[)') WITH &&
            ) WHERE (status = 'SCHEDULED'),
            CONSTRAINT ex_training_session_trainer_time EXCLUDE USING gist (
                trainer_id WITH =,
                tstzrange(starts_at, ends_at, '[)') WITH &&
            ) WHERE (status = 'SCHEDULED')
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_training_session_starts_at_id ON public.training_session (starts_at, id)"
    )
    op.execute(
        "CREATE INDEX ix_training_session_trainer_starts_at ON public.training_session (trainer_id, starts_at)"
    )


def downgrade() -> None:
    """Drop session data in a disposable target while retaining the potentially shared extension."""
    op.execute("DROP TABLE public.training_session")
