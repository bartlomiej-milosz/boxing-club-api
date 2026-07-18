"""Validate login requests and map credential outcomes to HTTP responses."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError

from boxing_club_api.application.errors import ErrorResponse, error_response
from boxing_club_api.core.pagination import Page
from boxing_club_api.db.session import SessionFactory

from .accounts import create_account, get_me, list_accounts
from .authentication import revoke_session
from .dependencies import CurrentPrincipal, DatabaseSessions
from .fields import normalize_email
from .login import create_login_session
from .passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from .schemas import CreateUserRequest, TrainerResponse, UpdateTrainerRequest, UserResponse
from .trainers import list_trainers, update_trainer

identity_router = APIRouter(prefix="/api/v1", tags=["identity"])

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Bounded login credentials with normalized email and rejected unknown fields."""

    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(max_length=254)]
    password: Annotated[
        SecretStr, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        """Apply the same email normalization used when accounts are created."""
        return normalize_email(value)


class LoginResponse(BaseModel):
    """One-time bearer credential and expiry returned after a successful login."""

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
    """Issue a bearer token or return a generic credential or database-availability error."""
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


@router.post("/logout", status_code=204)
def logout(principal: CurrentPrincipal, sessions: DatabaseSessions) -> Response:
    """Revoke the current bearer token while preserving other login sessions."""
    revoke_session(sessions, principal)
    return Response(status_code=204)


@identity_router.get("/me", response_model=UserResponse)
def me(principal: CurrentPrincipal, sessions: DatabaseSessions) -> UserResponse:
    """Return the caller's account identity and roles without exposing credential data."""
    return UserResponse.model_validate(get_me(sessions, principal))


@identity_router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    payload: CreateUserRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    response: Response,
) -> UserResponse:
    """Create MEMBER/TRAINER accounts for an owner and return their resource location."""
    result = create_account(
        sessions,
        principal,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password=payload.initial_password.get_secret_value(),
        roles=frozenset(payload.roles),
        trainer_bio=payload.trainer_bio,
    )
    response.headers["Location"] = f"/api/v1/users/{result.id}"
    return UserResponse.model_validate(result)


@identity_router.get("/users", response_model=Page[UserResponse])
def users(
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    role: Literal["OWNER", "TRAINER", "MEMBER"] | None = None,
) -> Page[UserResponse]:
    """List accounts for an owner with bounded pagination and an optional role filter."""
    items, total = list_accounts(sessions, principal, page=page, size=size, role=role)
    return Page(
        items=[UserResponse.model_validate(item) for item in items],
        page=page,
        size=size,
        total_items=total,
    )


@identity_router.get("/trainers", response_model=Page[TrainerResponse])
def trainers(
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    include_inactive: bool = False,
) -> Page[TrainerResponse]:
    """List active trainers for authenticated users; owners may request inactive profiles."""
    items, total = list_trainers(
        sessions, principal, page=page, size=size, include_inactive=include_inactive
    )
    return Page(
        items=[TrainerResponse.model_validate(item) for item in items],
        page=page,
        size=size,
        total_items=total,
    )


@identity_router.patch("/trainers/{trainer_id}", response_model=TrainerResponse)
def patch_trainer(
    trainer_id: UUID,
    payload: UpdateTrainerRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
) -> TrainerResponse:
    """Let an owner change only a trainer's biography and active state."""
    result = update_trainer(
        sessions, principal, trainer_id, changes=payload.model_dump(exclude_unset=True)
    )
    return TrainerResponse.model_validate(result)
