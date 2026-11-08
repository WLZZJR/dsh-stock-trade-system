"""Authentication value types (P1-23). Pure: no I/O, no framework imports (D7)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UserRecord:
    """A user with the workspace and role they sign in to."""

    id: uuid.UUID
    email: str
    password_hash: str
    status: str  # 'active' | 'disabled'
    workspace_id: uuid.UUID
    role: str  # 'owner' | 'researcher' | 'viewer'


@dataclass(frozen=True)
class SessionLookup:
    """A stored session joined with its user; validity is decided by the service."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    user_status: str
    workspace_id: uuid.UUID
    role: str
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class Identity:
    """Who is calling. ``workspace_id`` always comes from here, never from request input."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    workspace_id: uuid.UUID
    role: str
