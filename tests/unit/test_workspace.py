"""P1-24: a workspace resource is visible only inside its own workspace."""

from __future__ import annotations

import uuid

import pytest

from application import problems
from application.problems import ProblemError
from application.workspace import NOT_FOUND_DETAIL, require_in_workspace
from domain.auth import Identity

WORKSPACE_A = uuid.uuid4()
WORKSPACE_B = uuid.uuid4()


def identity(workspace_id: uuid.UUID) -> Identity:
    return Identity(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        email="user@example.com",
        workspace_id=workspace_id,
        role="owner",
    )


def test_a_resource_in_the_callers_workspace_passes() -> None:
    require_in_workspace(identity(WORKSPACE_A), WORKSPACE_A)


def test_a_resource_in_another_workspace_is_not_found() -> None:
    with pytest.raises(ProblemError) as exc:
        require_in_workspace(identity(WORKSPACE_A), WORKSPACE_B)
    assert exc.value.spec is problems.NOT_FOUND
    assert exc.value.detail == NOT_FOUND_DETAIL


def test_a_resource_without_a_workspace_is_not_found() -> None:
    with pytest.raises(ProblemError) as exc:
        require_in_workspace(identity(WORKSPACE_A), None)
    assert exc.value.spec is problems.NOT_FOUND


def test_missing_and_foreign_resources_are_indistinguishable() -> None:
    """No existence oracle: the same status and wording whether it exists elsewhere or not."""
    errors = []
    for resource_workspace in (WORKSPACE_B, None):
        with pytest.raises(ProblemError) as exc:
            require_in_workspace(identity(WORKSPACE_A), resource_workspace)
        errors.append((exc.value.spec, exc.value.detail, exc.value.extensions))
    assert errors[0] == errors[1]
