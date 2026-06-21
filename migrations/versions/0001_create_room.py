"""Create the room catalog table."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.room (
            id uuid NOT NULL,
            name varchar(100) NOT NULL,
            capacity integer NOT NULL,
            active boolean NOT NULL DEFAULT true,
            CONSTRAINT pk_room PRIMARY KEY (id),
            CONSTRAINT uq_room_name UNIQUE (name),
            CONSTRAINT ck_room_name_trimmed
                CHECK (name <> '' AND name !~ '^[[:space:]]|[[:space:]]$'),
            CONSTRAINT ck_room_capacity_positive CHECK (capacity > 0)
        )
        """
    )


def downgrade() -> None:
    """Remove the room table and its data in a disposable database."""
    op.execute("DROP TABLE public.room")
