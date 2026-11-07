"""raw_payloads and ingest_log (P1-15)

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Content-addressed storage (ADR-0011): identical responses are kept once per provider.
    # retention = 'hash_only' keeps only the hash, for providers whose licence forbids storing
    # responses; the CHECK makes the two states mutually exclusive.
    op.execute(
        """
        CREATE TABLE raw_payloads (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
          payload_json JSONB,
          payload_hash CHAR(64) NOT NULL,
          retention TEXT NOT NULL DEFAULT 'stored' CHECK (retention IN ('stored', 'hash_only')),
          first_received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          published_at TIMESTAMPTZ,
          license_scope TEXT,
          UNIQUE (provider_id, payload_hash),
          CONSTRAINT chk_raw_payload_retention CHECK (
            (retention = 'stored' AND payload_json IS NOT NULL) OR
            (retention = 'hash_only' AND payload_json IS NULL)
          )
        )
        """
    )
    # One row per fetch attempt (failures, retries and duplicate content included): the
    # observation history that raw_payloads deliberately does not keep.
    op.execute(
        """
        CREATE TABLE ingest_log (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
          endpoint TEXT NOT NULL,
          request_hash TEXT NOT NULL,
          requested_at TIMESTAMPTZ NOT NULL,
          received_at TIMESTAMPTZ,
          http_status INTEGER,
          payload_id UUID REFERENCES raw_payloads(id) ON DELETE RESTRICT,
          error_code TEXT,
          error_message TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0,
          response_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ingest_log_provider_time ON ingest_log(provider_id, requested_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ingest_log")
    op.execute("DROP TABLE raw_payloads")
