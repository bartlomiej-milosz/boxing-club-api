"""Define explicit account responses that exclude stored credentials and session digests."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Account identity and roles exposed by authenticated account endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    roles: list[str]
