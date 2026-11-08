"""POST /auth/login, POST /auth/logout, GET /auth/me (D1; see API_CONTRACT 24.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from api.deps import SESSION_COOKIE, get_auth_service, get_settings, require_session
from api.problem_http import problem_responses
from application.auth import AuthService
from application.config import Settings
from domain.auth import Identity

public_router = APIRouter(prefix="/auth", tags=["auth"])
private_router = APIRouter(prefix="/auth", tags=["auth"])

NO_STORE = "no-store"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)  # bounds the hashing work per request


class UserOut(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    workspace_id: uuid.UUID


class LoginResponse(BaseModel):
    user: UserOut
    expires_at: datetime


def _cookie_flags(settings: Settings) -> dict[str, object]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.env == "prod",  # TLS is mandatory in production (API_CONTRACT 24.1)
        "path": "/",
    }


@public_router.post(
    "/login", response_model=LoginResponse, responses=problem_responses(401, 422, 429)
)
def login(
    body: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    result = service.login(body.email, body.password)
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=settings.session_ttl_minutes * 60,
        **_cookie_flags(settings),  # type: ignore[arg-type]
    )
    response.headers["Cache-Control"] = NO_STORE
    return LoginResponse(
        user=UserOut(
            user_id=result.user_id,
            email=result.email,
            role=result.role,
            workspace_id=result.workspace_id,
        ),
        expires_at=result.expires_at,
    )


@private_router.post("/logout", status_code=204)
def logout(
    identity: Annotated[Identity, Depends(require_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    service.logout(identity)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, **_cookie_flags(settings))  # type: ignore[arg-type]
    return response


@private_router.get("/me", response_model=UserOut)
def me(identity: Annotated[Identity, Depends(require_session)], response: Response) -> UserOut:
    response.headers["Cache-Control"] = NO_STORE
    return UserOut(
        user_id=identity.user_id,
        email=identity.email,
        role=identity.role,
        workspace_id=identity.workspace_id,
    )
