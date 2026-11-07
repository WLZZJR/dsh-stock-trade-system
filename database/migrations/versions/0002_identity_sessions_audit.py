"""workspaces, users, workspace_members, auth_sessions, audit_logs (P1-11)

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MVP-1 is single-user, but workspace_id / user_id foreign keys exist from the start
    # (DATABASE.md 16.1: they must not be downgraded to bare UUID columns).
    op.execute(
        """
        CREATE TABLE workspaces (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name TEXT NOT NULL,
          settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE users (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE workspace_members (
          workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          role TEXT NOT NULL CHECK (role IN ('owner', 'researcher', 'viewer')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (workspace_id, user_id)
        )
        """
    )
    # Only the SHA-256 of the session token is stored, never the token itself (D3).
    op.execute(
        """
        CREATE TABLE auth_sessions (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash CHAR(64) NOT NULL UNIQUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ NOT NULL,
          revoked_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit_logs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          workspace_id UUID REFERENCES workspaces(id) ON DELETE RESTRICT,
          actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'service', 'system')),
          actor_id UUID,
          action TEXT NOT NULL,
          resource_type TEXT NOT NULL,
          resource_id UUID,
          details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_append_only
          BEFORE UPDATE OR DELETE ON audit_logs
          FOR EACH ROW EXECUTE FUNCTION trg_forbid_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE audit_logs")
    op.execute("DROP TABLE auth_sessions")
    op.execute("DROP TABLE workspace_members")
    op.execute("DROP TABLE users")
    op.execute("DROP TABLE workspaces")
