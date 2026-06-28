"""Create users, roles, profiles and authentication sessions."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.app_user (
            id uuid NOT NULL,
            email varchar(254) NOT NULL,
            password_hash text NOT NULL,
            first_name varchar(100) NOT NULL,
            last_name varchar(100) NOT NULL,
            status varchar(7) NOT NULL,
            created_at timestamptz NOT NULL,
            CONSTRAINT pk_app_user PRIMARY KEY (id),
            CONSTRAINT uq_app_user_email UNIQUE (email),
            CONSTRAINT ck_app_user_email_normalized
                CHECK (email <> '' AND email = lower(email) AND email !~ '[[:space:]]'),
            CONSTRAINT ck_app_user_first_name
                CHECK (first_name <> '' AND first_name !~ '^[[:space:]]|[[:space:]]$'),
            CONSTRAINT ck_app_user_last_name
                CHECK (last_name <> '' AND last_name !~ '^[[:space:]]|[[:space:]]$'),
            CONSTRAINT ck_app_user_status CHECK (status IN ('ACTIVE', 'BLOCKED'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public.user_role (
            user_id uuid NOT NULL,
            role varchar(7) NOT NULL,
            CONSTRAINT pk_user_role PRIMARY KEY (user_id, role),
            CONSTRAINT fk_user_role_user FOREIGN KEY (user_id) REFERENCES public.app_user (id),
            CONSTRAINT ck_user_role_role CHECK (role IN ('OWNER', 'TRAINER', 'MEMBER'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public.member_profile (
            user_id uuid NOT NULL,
            joined_on date NOT NULL,
            CONSTRAINT pk_member_profile PRIMARY KEY (user_id),
            CONSTRAINT fk_member_profile_user
                FOREIGN KEY (user_id) REFERENCES public.app_user (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public.trainer_profile (
            user_id uuid NOT NULL,
            bio text,
            active boolean NOT NULL,
            CONSTRAINT pk_trainer_profile PRIMARY KEY (user_id),
            CONSTRAINT fk_trainer_profile_user
                FOREIGN KEY (user_id) REFERENCES public.app_user (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public.auth_session (
            id uuid NOT NULL,
            user_id uuid NOT NULL,
            token_digest char(64) NOT NULL,
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            CONSTRAINT pk_auth_session PRIMARY KEY (id),
            CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id) REFERENCES public.app_user (id),
            CONSTRAINT uq_auth_session_token_digest UNIQUE (token_digest),
            CONSTRAINT ck_auth_session_token_digest CHECK (token_digest ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_auth_session_expiry CHECK (expires_at > created_at)
        )
        """
    )
    op.execute("CREATE INDEX ix_auth_session_user_id ON public.auth_session (user_id)")


def downgrade() -> None:
    """Remove identity data in a disposable database."""
    op.execute("DROP TABLE public.auth_session")
    op.execute("DROP TABLE public.trainer_profile")
    op.execute("DROP TABLE public.member_profile")
    op.execute("DROP TABLE public.user_role")
    op.execute("DROP TABLE public.app_user")
