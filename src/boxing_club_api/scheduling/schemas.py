"""Validate room catalog requests and expose explicit credential-free results."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from boxing_club_api.identity.fields import normalize_name


class RoomResponse(BaseModel):
    """Room identity, name, fixed capacity and catalog activity state."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    capacity: int
    active: bool


class CreateRoomRequest(BaseModel):
    """Bounded room input with positive integer capacity and default active state."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)]
    capacity: Annotated[int, Field(gt=0, le=2147483647, strict=True)]
    active: bool = True

    @field_validator("name")
    @classmethod
    def normalize_room_name(cls, value: str) -> str:
        """Trim catalog names and reject whitespace-only values."""
        return normalize_name(value)


class UpdateRoomRequest(BaseModel):
    """Partial name/activity update that excludes capacity changes and explicit nulls."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_room_name(cls, value: str | None) -> str | None:
        """Normalize an explicitly supplied room name."""
        return normalize_name(value) if value is not None else None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        """Require at least one change and reject null values for non-nullable room fields."""
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Supply a non-null room name or active value.")
        return self
