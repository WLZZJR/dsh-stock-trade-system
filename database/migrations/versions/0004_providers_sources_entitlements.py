"""providers, data_sources, provider_entitlements, provider_coverage (P1-13)

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE providers (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name TEXT NOT NULL UNIQUE,
          provider_type TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          base_url TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE data_sources (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          provider_id UUID REFERENCES providers(id) ON DELETE RESTRICT,
          source_name TEXT NOT NULL,
          source_type TEXT NOT NULL,
          source_url TEXT,
          license_scope TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Minimum authorisation by default (ADR-0014): nothing may be persisted, sent to an LLM or
    # redistributed until the project owner signs off a licence review.
    op.execute(
        """
        CREATE TABLE provider_entitlements (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
          workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
          license_type TEXT NOT NULL,
          allowed_use TEXT NOT NULL,
          persistence_allowed BOOLEAN NOT NULL DEFAULT false,
          llm_transmission_allowed BOOLEAN NOT NULL DEFAULT false,
          redistribution_allowed BOOLEAN NOT NULL DEFAULT false,
          contract_version TEXT,
          expires_at TIMESTAMPTZ,
          UNIQUE (provider_id, workspace_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE provider_coverage (
          provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
          market_code TEXT NOT NULL,
          dataset TEXT NOT NULL,
          coverage_status TEXT NOT NULL
            CHECK (coverage_status IN ('supported', 'partial', 'unsupported', 'unverified')),
          checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (provider_id, market_code, dataset)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE provider_coverage")
    op.execute("DROP TABLE provider_entitlements")
    op.execute("DROP TABLE data_sources")
    op.execute("DROP TABLE providers")
