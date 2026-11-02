from fastapi import FastAPI

from .health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="boxing-club-api", version="0.1.0")
    app.include_router(health_router)
    return app
