from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError

from boxing_club_api.application.errors import ErrorResponse, error_response
from boxing_club_api.db.session import SessionFactory

from .fields import normalize_email
from .login import create_login_session
from .passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(max_length=254)]
    password: Annotated[
        SecretStr, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def login(
    credentials: LoginRequest, request: Request, response: Response
) -> LoginResponse | Response:
    sessions: SessionFactory | None = request.app.state.db_sessions
    if sessions is not None:
        try:
            result = create_login_session(
                sessions, credentials.email, credentials.password.get_secret_value()
            )
        except OperationalError, InterfaceError, TimeoutError:
            pass
        else:
            if result is None:
                return error_response(401, "INVALID_CREDENTIALS", "Invalid email or password.")

            response.headers["Cache-Control"] = "no-store"
            return LoginResponse(access_token=result.access_token, expires_at=result.expires_at)

    return error_response(503, "TEMPORARILY_UNAVAILABLE", "Login is temporarily unavailable.")
