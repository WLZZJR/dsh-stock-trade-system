"""P1-24: user A cannot read, list or write into user B's workspace (two real workspaces)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.deps import (
    get_connection,
    get_password_hasher,
    get_settings,
    get_workspace_id,
    require_session,
)
from api.main import create_app
from application.config import Settings
from application.owner import create_owner
from application.security import hash_password
from application.workspace import NOT_FOUND_DETAIL, require_in_workspace
from data_engine.auth_repository import PgAuthRepository
from domain.auth import Identity

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery staple"  # noqa: S105 - fixture value, not a credential
A_EMAIL = "alice@example.com"
B_EMAIL = "bob@example.com"


class NoteIn(BaseModel):
    body: str
    workspace_id: uuid.UUID | None = None  # a hostile client may try to choose the workspace


def build_app(db: Conn) -> Any:
    """The real app plus a throw-away workspace-scoped resource written the intended way."""
    app = create_app()
    app.dependency_overrides[get_connection] = lambda: db
    app.dependency_overrides[get_password_hasher] = lambda: FAST
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://unused/unused",  # type: ignore[arg-type]
        redis_url="redis://unused/0",  # type: ignore[arg-type]
    )

    def get_note(
        note_id: uuid.UUID,
        identity: Identity = Depends(require_session),  # noqa: B008
    ) -> dict[str, str]:
        row = db.execute(
            "SELECT workspace_id, body FROM notes WHERE id = %s", (note_id,)
        ).fetchone()
        require_in_workspace(identity, row[0] if row else None)
        assert row is not None
        return {"body": str(row[1])}

    def list_notes(
        workspace_id: uuid.UUID | None = None,  # ignored on purpose
        mine: uuid.UUID = Depends(get_workspace_id),  # noqa: B008
    ) -> list[str]:
        rows = db.execute(
            "SELECT body FROM notes WHERE workspace_id = %s ORDER BY body", (mine,)
        ).fetchall()
        return [str(r[0]) for r in rows]

    def create_note(
        note: NoteIn,
        mine: uuid.UUID = Depends(get_workspace_id),  # noqa: B008
    ) -> dict[str, str]:
        row = db.execute(
            "INSERT INTO notes (workspace_id, body) VALUES (%s, %s) RETURNING id", (mine, note.body)
        ).fetchone()
        assert row is not None
        return {"id": str(row[0])}

    deps = [Depends(require_session)]
    app.add_api_route("/api/v1/_t/notes/{note_id}", get_note, methods=["GET"], dependencies=deps)
    app.add_api_route("/api/v1/_t/notes", list_notes, methods=["GET"], dependencies=deps)
    app.add_api_route("/api/v1/_t/notes", create_note, methods=["POST"], dependencies=deps)
    return app


def login(app: Any, email: str) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)  # one cookie jar per user
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def world(db: Conn) -> tuple[TestClient, TestClient, uuid.UUID, uuid.UUID]:
    db.execute(
        "CREATE TEMP TABLE notes (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
        "workspace_id uuid NOT NULL, body text NOT NULL)"
    )
    alice = create_owner(
        PgAuthRepository(db), A_EMAIL, PASSWORD, hasher=FAST, now=datetime.now(UTC)
    )
    workspace_b = db.execute("INSERT INTO workspaces (name) VALUES ('Bob') RETURNING id").fetchone()
    user_b = db.execute(
        "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
        (B_EMAIL, hash_password(PASSWORD, FAST)),
    ).fetchone()
    assert workspace_b is not None and user_b is not None
    db.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, 'owner')",
        (workspace_b[0], user_b[0]),
    )
    app = build_app(db)
    return login(app, A_EMAIL), login(app, B_EMAIL), alice.workspace_id, workspace_b[0]


def seed_note(db: Conn, workspace_id: uuid.UUID, body: str) -> uuid.UUID:
    row = db.execute(
        "INSERT INTO notes (workspace_id, body) VALUES (%s, %s) RETURNING id", (workspace_id, body)
    ).fetchone()
    assert row is not None
    return row[0]  # type: ignore[no-any-return]


def test_each_user_sees_their_own_workspace_id(
    world: tuple[TestClient, TestClient, uuid.UUID, uuid.UUID],
) -> None:
    alice, bob, ws_a, ws_b = world
    assert ws_a != ws_b
    assert alice.get("/api/v1/auth/me").json()["workspace_id"] == str(ws_a)
    assert bob.get("/api/v1/auth/me").json()["workspace_id"] == str(ws_b)


def test_user_can_read_their_own_resource_but_not_the_other_workspaces(
    world: tuple[TestClient, TestClient, uuid.UUID, uuid.UUID], db: Conn
) -> None:
    alice, bob, ws_a, _ = world
    note = seed_note(db, ws_a, "alice only")
    assert alice.get(f"/api/v1/_t/notes/{note}").json() == {"body": "alice only"}
    response = bob.get(f"/api/v1/_t/notes/{note}")
    assert response.status_code == 404
    assert "alice only" not in response.text


def test_foreign_and_nonexistent_resources_are_indistinguishable(
    world: tuple[TestClient, TestClient, uuid.UUID, uuid.UUID], db: Conn
) -> None:
    alice, bob, ws_a, _ = world
    foreign = bob.get(f"/api/v1/_t/notes/{seed_note(db, ws_a, 'secret')}")
    missing = bob.get(f"/api/v1/_t/notes/{uuid.uuid4()}")
    assert foreign.status_code == missing.status_code == 404
    strip = lambda r: {k: v for k, v in r.json().items() if k != "trace_id"}  # noqa: E731
    assert strip(foreign) == strip(missing)
    assert foreign.json()["detail"] == NOT_FOUND_DETAIL
    assert alice.get("/api/v1/auth/me").status_code == 200  # alice is unaffected


def test_lists_contain_only_the_callers_rows(
    world: tuple[TestClient, TestClient, uuid.UUID, uuid.UUID], db: Conn
) -> None:
    alice, bob, ws_a, ws_b = world
    seed_note(db, ws_a, "a1")
    seed_note(db, ws_a, "a2")
    seed_note(db, ws_b, "b1")
    assert alice.get("/api/v1/_t/notes").json() == ["a1", "a2"]
    assert bob.get("/api/v1/_t/notes").json() == ["b1"]


def test_a_workspace_id_in_the_query_string_is_ignored(
    world: tuple[TestClient, TestClient, uuid.UUID, uuid.UUID], db: Conn
) -> None:
    _, bob, ws_a, ws_b = world
    seed_note(db, ws_a, "a1")
    seed_note(db, ws_b, "b1")
    assert bob.get("/api/v1/_t/notes", params={"workspace_id": str(ws_a)}).json() == ["b1"]


def test_a_workspace_id_in_the_body_cannot_choose_where_data_is_written(
    world: tuple[TestClient, TestClient, uuid.UUID, uuid.UUID], db: Conn
) -> None:
    alice, bob, ws_a, ws_b = world
    response = bob.post("/api/v1/_t/notes", json={"body": "planted", "workspace_id": str(ws_a)})
    assert response.status_code == 200
    assert alice.get("/api/v1/_t/notes").json() == []  # nothing landed in alice's workspace
    assert bob.get("/api/v1/_t/notes").json() == ["planted"]
    row = db.execute("SELECT workspace_id FROM notes WHERE body = 'planted'").fetchone()
    assert row == (ws_b,)


def test_without_a_session_nothing_is_reachable(db: Conn) -> None:
    db.execute("CREATE TEMP TABLE notes (id uuid, workspace_id uuid, body text)")
    anonymous = TestClient(build_app(db), raise_server_exceptions=False)
    assert anonymous.get("/api/v1/_t/notes").status_code == 401
    assert anonymous.get(f"/api/v1/_t/notes/{uuid.uuid4()}").status_code == 401
    assert anonymous.post("/api/v1/_t/notes", json={"body": "x"}).status_code == 401
