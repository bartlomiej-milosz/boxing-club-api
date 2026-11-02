from fastapi import APIRouter

router = APIRouter()


@router.get(path="/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}
