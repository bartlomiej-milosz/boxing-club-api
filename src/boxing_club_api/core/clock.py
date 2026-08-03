"""Provide an injectable UTC clock for decisions made after database locks."""

from collections.abc import Callable
from datetime import UTC, datetime

type Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Read the current offset-aware UTC instant."""
    return datetime.now(UTC)
