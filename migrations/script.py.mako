"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from collections.abc import Sequence

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Author the explicit SQL for this change before applying the revision."""
    raise NotImplementedError("Write and review this migration before applying it")


def downgrade() -> None:
    """Document and implement reversal only when safe for this revision."""
    raise NotImplementedError("Write and review the reversal policy first")
