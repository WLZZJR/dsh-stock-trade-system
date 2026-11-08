from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.middleware import RequestContextMiddleware
from api.problem_http import register_problem_handlers
from application.config import load_settings
from application.observability import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on bad configuration; ConfigError messages never echo secret values.
    configure_logging(load_settings().log_level)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="GEI API", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_problem_handlers(app)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
