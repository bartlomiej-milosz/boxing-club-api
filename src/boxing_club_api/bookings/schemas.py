"""Validate member-owned requests and expose limited reservation audit results."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReserveRequest(BaseModel):
    """Class selection only; the server derives member identity from the bearer principal."""

    model_config = ConfigDict(extra="forbid")
    session_id: UUID


class BookingResponse(BaseModel):
    """Role-safe reservation facts with cancellation audit and no contact information."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    member_id: UUID
    session_id: UUID
    status: Literal["RESERVED", "CANCELLED"]
    created_at: datetime
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason: str | None


class CancelBookingRequest(BaseModel):
    """Optional member reason, trimmed and limited to 1000 characters."""

    model_config = ConfigDict(extra="forbid")
    reason: Annotated[str | None, Field(max_length=1000)] = None

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        """Treat an empty optional reason as absent and reject embedded NUL characters."""
        if value is None:
            return None
        if "\x00" in value:
            raise ValueError("Invalid cancellation reason.")
        return value.strip() or None


class RosterResponse(BaseModel):
    """Minimum participant display fields permitted for an owner or assigned trainer."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    member_id: UUID
    first_name: str
    last_name: str
    status: Literal["RESERVED", "CANCELLED"]
    created_at: datetime
