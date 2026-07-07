"""Expose a process liveness check that works independently of PostgreSQL."""

from fastapi import APIRouter

router = APIRouter()


@router.get(path="/health/live")
def health_live() -> dict[str, str]:
    """Report that the process can serve requests without querying the database."""
    return {"status": "ok"}
