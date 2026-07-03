from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    error = ErrorResponse(code=code, message=message, request_id=str(uuid4()))
    return JSONResponse(status_code=status_code, content=error.model_dump())


def invalid_request(_request: Request, _error: Exception) -> JSONResponse:
    # Pydantic's raw errors may contain the original input, including a password.
    return error_response(422, "VALIDATION_ERROR", "Request data is invalid.")
