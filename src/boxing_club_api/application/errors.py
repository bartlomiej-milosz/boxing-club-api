"""Build consistent HTTP errors without exposing submitted credentials."""

from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from boxing_club_api.core.errors import ApplicationError

from .correlation import request_id


class ErrorResponse(BaseModel):
    """Public error envelope with a correlation identifier and no internal diagnostics."""

    code: str
    message: str
    request_id: str


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Build a JSON error with a fresh request identifier."""
    error = ErrorResponse(code=code, message=message, request_id=request_id.get() or str(uuid4()))
    return JSONResponse(status_code=status_code, content=error.model_dump())


def invalid_request(_request: Request, _error: Exception) -> JSONResponse:
    # Pydantic's raw errors may contain the original input, including a password.
    """Reject invalid request data without echoing Pydantic inputs or secrets."""
    return error_response(422, "VALIDATION_ERROR", "Request data is invalid.")


def operation_failed(_request: Request, error: Exception) -> JSONResponse:
    """Translate an expected operation failure into the common public error envelope."""
    assert isinstance(error, ApplicationError)
    response = error_response(error.status_code, error.code, str(error))
    if error.status_code == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


def database_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    """Hide database connection and lock diagnostics behind a stable transient response."""
    return error_response(
        503, "TEMPORARILY_UNAVAILABLE", "The database is temporarily unavailable."
    )


def http_failure(_request: Request, error: Exception) -> JSONResponse:
    """Return the common envelope for unmatched routes and unsupported HTTP methods."""
    assert isinstance(error, HTTPException)
    code = "RESOURCE_NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR"
    message = "Resource not found." if error.status_code == 404 else "HTTP request failed."
    response = error_response(error.status_code, code, message)
    if error.headers:
        response.headers.update(error.headers)
    return response
