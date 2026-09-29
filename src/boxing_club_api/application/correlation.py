"""Carry one server-generated correlation identifier through each request."""

from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


async def correlate(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Assign a request ID shared by the response header and any public error envelope."""
    identifier = str(uuid4())
    token = request_id.set(identifier)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = identifier
        return response
    finally:
        request_id.reset(token)
