"""Define explicit account responses that exclude stored credentials and session digests."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .fields import normalize_email, normalize_name
from .passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

type TrainerBio = Annotated[str, Field(pattern=r"^[^\x00]*$")]


class UserResponse(BaseModel):
    """Account identity and roles exposed by authenticated account endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    roles: list[str]


class CreateUserRequest(BaseModel):
    """Owner-supplied account details with bounded credentials and MEMBER/TRAINER roles."""

    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(max_length=254)]
    initial_password: Annotated[
        SecretStr, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    roles: Annotated[set[Literal["MEMBER", "TRAINER"]], Field(min_length=1, max_length=2)]
    trainer_bio: TrainerBio | None = None

    @field_validator("email")
    @classmethod
    def normalize_account_email(cls, value: str) -> str:
        """Apply the common email policy before account creation."""
        return normalize_email(value)

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_account_name(cls, value: str) -> str:
        """Trim names and reject blank or invalid account names."""
        return normalize_name(value)

    @model_validator(mode="after")
    def validate_trainer_bio(self) -> Self:
        """Require the TRAINER role when a trainer biography is supplied."""
        if self.trainer_bio is not None and "TRAINER" not in self.roles:
            raise ValueError("A trainer bio requires the TRAINER role.")
        return self


class TrainerResponse(BaseModel):
    """Catalog-safe trainer fields, including active state for owner administration."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    bio: str | None
    active: bool


class UpdateTrainerRequest(BaseModel):
    """Partial biography or active-state update with unknown fields and null active rejected."""

    model_config = ConfigDict(extra="forbid")

    bio: TrainerBio | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        """Distinguish an omitted field from an explicit biography clear or invalid active null."""
        if not self.model_fields_set or ("active" in self.model_fields_set and self.active is None):
            raise ValueError("Supply bio or a non-null active value.")
        return self
