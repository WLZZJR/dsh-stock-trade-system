"""extensions, trg_forbid_mutation, currencies (P1-10)

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # Shared guard for append-only / immutable tables. It must exist before any table that
    # attaches it (audit_logs, data_snapshots, ...), hence it lives in the first migration.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_forbid_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
          RAISE EXCEPTION '% is append-only; create a new version instead', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )

    op.execute(
        """
        CREATE TABLE currencies (
          code CHAR(3) PRIMARY KEY,
          name TEXT NOT NULL,
          minor_unit SMALLINT NOT NULL DEFAULT 2
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE currencies")
    op.execute("DROP FUNCTION trg_forbid_mutation()")
    op.execute("DROP EXTENSION btree_gist")
    op.execute("DROP EXTENSION pgcrypto")
