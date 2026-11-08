from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI

from api.deps import require_session
from api.middleware import RequestContextMiddleware
from api.problem_http import (
    install_problem_openapi,
    problem_responses,
    register_problem_handlers,
)
from api.routes import auth, health, instruments, meta
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
    # FastAPI's public /docs, /redoc and /openapi.json are off: the schema is served at
    # /api/v1/openapi.json behind the session instead (routes/meta.py).
    app = FastAPI(
        title="GEI API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(RequestContextMiddleware)
    register_problem_handlers(app)
    install_problem_openapi(app)
    app.include_router(health.router)  # probes: public, carry no data
    # Login is the only public API route. Everything else sits behind the session dependency;
    # tests/security/test_routes_require_session.py fails if a route is added without it.
    app.include_router(auth.public_router, prefix=API_PREFIX)
    protected: dict[str, Any] = {
        "dependencies": [Depends(require_session)],
        "responses": problem_responses(401),
    }
    app.include_router(auth.private_router, prefix=API_PREFIX, **protected)
    app.include_router(instruments.router, prefix=API_PREFIX, **protected)
    app.include_router(meta.router, prefix=API_PREFIX, **protected)

    return app


app = create_app()
