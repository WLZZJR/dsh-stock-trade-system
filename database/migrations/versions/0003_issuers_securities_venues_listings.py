"""issuers, securities, venues, listings (P1-12)

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE issuers (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          legal_name TEXT NOT NULL,
          common_name TEXT,
          country_code CHAR(2),
          sector TEXT,
          industry TEXT,
          lei TEXT,
          website TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE securities (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          issuer_id UUID NOT NULL REFERENCES issuers(id) ON DELETE RESTRICT,
          security_type TEXT NOT NULL,
          share_class TEXT,
          description TEXT,
          nominal_currency CHAR(3) REFERENCES currencies(code),
          adr_ratio NUMERIC(18,6), -- ordinary shares per ADR (NULL or 1 for non-ADR)
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE venues (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          mic VARCHAR(4) UNIQUE,
          name TEXT NOT NULL,
          country_code CHAR(2),
          timezone TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # valid_from defaults to CURRENT_DATE per the baseline DDL, but historical listings MUST
    # supply it explicitly: seeds and imports must never rely on this default (plan, stage B note).
    # The exclusion constraint also covers "same start date twice", so no extra UNIQUE (ADR-0016).
    op.execute(
        """
        CREATE TABLE listings (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          security_id UUID NOT NULL REFERENCES securities(id) ON DELETE RESTRICT,
          venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE RESTRICT,
          ticker TEXT NOT NULL,
          trading_currency CHAR(3) NOT NULL REFERENCES currencies(code),
          status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'suspended', 'delisted')),
          valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
          valid_to DATE NOT NULL DEFAULT '9999-12-31',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT chk_listings_valid_range CHECK (valid_from < valid_to),
          EXCLUDE USING gist (
            venue_id WITH =,
            ticker WITH =,
            daterange(valid_from, valid_to, '[)') WITH &&
          )
        )
        """
    )
    op.execute("CREATE INDEX idx_listings_ticker ON listings(ticker)")


def downgrade() -> None:
    op.execute("DROP TABLE listings")
    op.execute("DROP TABLE venues")
    op.execute("DROP TABLE securities")
    op.execute("DROP TABLE issuers")
