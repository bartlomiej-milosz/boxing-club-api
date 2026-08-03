"""Expose application-level resources without opening database transactions."""

from typing import Annotated

from fastapi import Depends, Request

from boxing_club_api.core.clock import Clock


def application_clock(request: Request) -> Clock:
    """Return the process clock, which tests may replace with a deterministic callable."""
    return request.app.state.clock


CurrentClock = Annotated[Clock, Depends(application_clock)]
