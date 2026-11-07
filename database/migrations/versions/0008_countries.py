"""countries reference table (P1-17)

The baseline DDL has no countries table, but the Phase 1 plan seeds ISO 3166 codes. The table is
a plain reference list: existing columns (issuers.country_code, venues.country_code) are not
turned into foreign keys, so the baseline contract is unchanged.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE countries (
          code CHAR(2) PRIMARY KEY,          -- ISO 3166-1 alpha-2
          alpha3 CHAR(3) NOT NULL UNIQUE,
          numeric_code CHAR(3) NOT NULL UNIQUE,
          name TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE countries")
