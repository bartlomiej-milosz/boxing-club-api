from fastapi import FastAPI

from boxing_club_api.core.settings import Settings

from .health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="boxing-club-api", version="0.1.0")
    app.state.app_env = Settings().app_env
    app.include_router(health_router)
    return app
