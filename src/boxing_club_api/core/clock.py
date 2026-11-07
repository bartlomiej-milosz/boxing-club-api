"""Provide an injectable UTC clock for decisions made after database locks."""

from collections.abc import Callable
from datetime import UTC, datetime

from .errors import ApplicationError

type Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Read the current offset-aware UTC instant."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Normalize an aware input to UTC or reject an unrepresentable instant with 422."""
    try:
        if value.utcoffset() is None:
            raise ValueError("A UTC offset is required.")
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ApplicationError(
            422, "VALIDATION_ERROR", "Timestamp must be representable in UTC with a UTC offset."
        ) from error
