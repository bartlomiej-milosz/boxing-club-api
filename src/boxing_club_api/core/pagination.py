"""Define the bounded, zero-based page envelope shared by list endpoints."""

from pydantic import BaseModel


class Page[T](BaseModel):
    """Items and total count for one explicitly requested page of a stable ordering."""

    items: list[T]
    page: int
    size: int
    total_items: int
