"""data_snapshots and data_snapshot_items (P1-16)

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Immutable snapshots (ADR-0010): every research / valuation run pins the exact inputs it used.
    op.execute(
        """
        CREATE TABLE data_snapshots (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
          snapshot_type TEXT NOT NULL,
          as_of TIMESTAMPTZ NOT NULL,
          schema_version TEXT NOT NULL,
          selection_policy JSONB NOT NULL,
          manifest JSONB NOT NULL,
          content_hash CHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Rows with a UUID are referenced one by one; market bars (composite key, large volume) are
    # referenced as a range. The CHECK keeps the two reference styles from being mixed up.
    op.execute(
        """
        CREATE TABLE data_snapshot_items (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          snapshot_id UUID NOT NULL REFERENCES data_snapshots(id) ON DELETE RESTRICT,
          record_type TEXT NOT NULL CHECK (record_type IN (
            'financial_fact', 'filing', 'corporate_action', 'fx_rate', 'market_bar_range',
            'valuation_assumption', 'peer_set'
          )),
          record_id UUID,
          range_ref_json JSONB,
          record_hash CHAR(64) NOT NULL,
          source_published_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT chk_snapshot_item_ref CHECK (
            (record_type = 'market_bar_range' AND range_ref_json IS NOT NULL
              AND record_id IS NULL) OR
            (record_type <> 'market_bar_range' AND record_id IS NOT NULL)
          )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_snapshot_items_record
          ON data_snapshot_items(snapshot_id, record_type, record_id)
          WHERE record_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshots_immutable
          BEFORE UPDATE OR DELETE ON data_snapshots
          FOR EACH ROW EXECUTE FUNCTION trg_forbid_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshot_items_immutable
          BEFORE UPDATE OR DELETE ON data_snapshot_items
          FOR EACH ROW EXECUTE FUNCTION trg_forbid_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE data_snapshot_items")
    op.execute("DROP TABLE data_snapshots")
