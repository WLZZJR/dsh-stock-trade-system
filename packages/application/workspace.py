"""Workspace ownership checks (P1-24), reused by every future workspace-scoped resource.

Rules for any code that serves a workspace resource:

1. the caller's workspace comes from the session (``Identity.workspace_id``) and nowhere else:
   never from a query parameter, path segment or request body;
2. list queries filter by that workspace id in SQL;
3. a single resource owned by another workspace is answered exactly like a missing one (404), so
   the API never confirms that someone else's resource exists.
"""

from __future__ import annotations

import uuid

from application import problems
from application.problems import ProblemError
from domain.auth import Identity

NOT_FOUND_DETAIL = "The requested resource was not found."


def require_in_workspace(identity: Identity, resource_workspace_id: uuid.UUID | None) -> None:
    """Raise 404 unless the resource belongs to the caller's workspace."""
    if resource_workspace_id is None or resource_workspace_id != identity.workspace_id:
        raise ProblemError(problems.NOT_FOUND, NOT_FOUND_DETAIL)
