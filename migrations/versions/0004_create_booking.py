"""Create reservations with retained cancellation history and active-booking uniqueness."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create booking constraints and indexes supporting locked seat counts and own history."""
    op.execute("""CREATE TABLE public.booking (
        id uuid NOT NULL,
        member_id uuid NOT NULL,
        session_id uuid NOT NULL,
        status varchar(9) NOT NULL,
        created_at timestamptz NOT NULL,
        cancelled_at timestamptz,
        cancelled_by_user_id uuid,
        cancellation_reason varchar(1000),
        CONSTRAINT pk_booking PRIMARY KEY (id),
        CONSTRAINT fk_booking_member FOREIGN KEY (member_id) REFERENCES public.member_profile (user_id),
        CONSTRAINT fk_booking_session FOREIGN KEY (session_id) REFERENCES public.training_session (id),
        CONSTRAINT fk_booking_cancelled_by FOREIGN KEY (cancelled_by_user_id) REFERENCES public.app_user (id),
        CONSTRAINT ck_booking_status CHECK (status IN ('RESERVED','CANCELLED')),
        CONSTRAINT ck_booking_cancellation_audit CHECK (
            (status='RESERVED' AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL AND cancellation_reason IS NULL)
            OR (status='CANCELLED' AND cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL)
        ),
        CONSTRAINT ck_booking_reason CHECK (cancellation_reason IS NULL OR
            (cancellation_reason<>'' AND cancellation_reason !~ '^[[:space:]]|[[:space:]]$'))
    )""")
    op.execute(
        "CREATE UNIQUE INDEX uq_booking_active_member_session ON public.booking (member_id,session_id) WHERE status <> 'CANCELLED'"
    )
    op.execute("CREATE INDEX ix_booking_session_status ON public.booking (session_id,status)")
    op.execute(
        "CREATE INDEX ix_booking_member_created_id ON public.booking (member_id,created_at,id)"
    )


def downgrade() -> None:
    """Remove reservations only when explicitly downgrading a disposable target."""
    op.execute("DROP TABLE public.booking")
