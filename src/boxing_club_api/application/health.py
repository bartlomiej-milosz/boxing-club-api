"""Expose a process liveness check that works independently of PostgreSQL."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from boxing_club_api.db.readiness import database_ready
from boxing_club_api.db.session import SessionFactory

router = APIRouter()


@router.get(path="/health/live")
def health_live() -> dict[str, str]:
    """Report that the process can serve requests without querying the database."""
    return {"status": "ok"}


@router.get("/health/ready", responses={503: {"description": "Database or schema unavailable"}})
def health_ready(request: Request) -> JSONResponse:
    """Report readiness only when the required database schema is reachable and current."""
    sessions: SessionFactory | None = request.app.state.db_sessions
    ready = sessions is not None and database_ready(sessions)
    return JSONResponse(
        status_code=200 if ready else 503, content={"status": "ok" if ready else "unavailable"}
    )
