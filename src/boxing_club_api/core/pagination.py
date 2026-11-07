"""Define the bounded, zero-based page envelope shared by list endpoints."""

from pydantic import BaseModel

from .errors import ApplicationError

MAX_OFFSET = 2**63 - 1


def page_offset(page: int, size: int) -> int:
    """Validate page bounds and return an offset representable by PostgreSQL bigint."""
    offset = page * size
    if page < 0 or not 1 <= size <= 100 or offset > MAX_OFFSET:
        raise ApplicationError(
            422,
            "VALIDATION_ERROR",
            "Use page >= 0, size between 1 and 100, and page * size <= 9223372036854775807.",
        )
    return offset


class Page[T](BaseModel):
    """Items and total count for one explicitly requested page of a stable ordering."""

    items: list[T]
    page: int
    size: int
    total_items: int
