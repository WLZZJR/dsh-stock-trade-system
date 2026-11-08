from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.middleware import RequestContextMiddleware
from api.problem_http import register_problem_handlers
from api.routes import instruments
from application.config import load_settings
from application.observability import configure_logging

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on bad configuration; ConfigError messages never echo secret values.
    settings = load_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="GEI API", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_problem_handlers(app)
    app.include_router(instruments.router, prefix=API_PREFIX)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
