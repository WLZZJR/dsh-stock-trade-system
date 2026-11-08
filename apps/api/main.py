from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from api.deps import require_session
from api.middleware import RequestContextMiddleware
from api.problem_http import register_problem_handlers
from api.routes import auth, instruments
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
    # Login is the only public API route. Everything else sits behind the session dependency;
    # tests/security/test_routes_require_session.py fails if a route is added without it.
    app.include_router(auth.public_router, prefix=API_PREFIX)
    protected = [Depends(require_session)]
    app.include_router(auth.private_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(instruments.router, prefix=API_PREFIX, dependencies=protected)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
