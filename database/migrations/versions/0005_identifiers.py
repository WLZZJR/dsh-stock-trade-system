"""identifiers with exclusion constraint and entity triggers (P1-14)

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ENTITY_TABLES = {
    "issuer": "issuers",
    "security": "securities",
    "listing": "listings",
    "venue": "venues",
}


def upgrade() -> None:
    # Polymorphic identifier table (ADR-0016). Referential integrity cannot be a plain foreign
    # key, so it is enforced by triggers in both directions below.
    op.execute(
        """
        CREATE TABLE identifiers (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          entity_type TEXT NOT NULL
            CHECK (entity_type IN ('issuer', 'security', 'listing', 'venue')),
          entity_id UUID NOT NULL,
          id_type TEXT NOT NULL CHECK (id_type IN (
            'isin', 'figi', 'composite_figi', 'share_class_figi',
            'cusip', 'sedol', 'lei', 'cik', 'local_code', 'vendor_symbol'
          )),
          id_value TEXT NOT NULL,
          source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE RESTRICT,
          valid_from TIMESTAMPTZ NOT NULL DEFAULT '-infinity',
          valid_to TIMESTAMPTZ NOT NULL DEFAULT 'infinity',
          observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT chk_identifiers_valid_range CHECK (valid_from < valid_to),
          -- The same identifier may never point at two things during the same period.
          EXCLUDE USING gist (
            entity_type WITH =,
            id_type WITH =,
            id_value WITH =,
            tstzrange(valid_from, valid_to, '[)') WITH &&
          )
        )
        """
    )
    op.execute("CREATE INDEX idx_identifiers_lookup ON identifiers(id_type, id_value)")
    op.execute("CREATE INDEX idx_identifiers_entity ON identifiers(entity_type, entity_id)")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_verify_identifier_entity()
        RETURNS TRIGGER AS $$
        DECLARE
          entity_exists BOOLEAN;
        BEGIN
          CASE NEW.entity_type
            WHEN 'issuer' THEN
              SELECT EXISTS(SELECT 1 FROM issuers WHERE id = NEW.entity_id) INTO entity_exists;
            WHEN 'security' THEN
              SELECT EXISTS(SELECT 1 FROM securities WHERE id = NEW.entity_id) INTO entity_exists;
            WHEN 'listing' THEN
              SELECT EXISTS(SELECT 1 FROM listings WHERE id = NEW.entity_id) INTO entity_exists;
            WHEN 'venue' THEN
              SELECT EXISTS(SELECT 1 FROM venues WHERE id = NEW.entity_id) INTO entity_exists;
            ELSE
              -- BEFORE triggers run ahead of CHECK constraints, so reject unknown types here with
              -- the same error code instead of leaking plpgsql's CASE_NOT_FOUND.
              RAISE EXCEPTION 'Unknown identifier entity_type: %', NEW.entity_type
                USING ERRCODE = 'check_violation';
          END CASE;

          IF NOT entity_exists THEN
            RAISE EXCEPTION 'Referenced entity (%: %) does not exist',
              NEW.entity_type, NEW.entity_id
              USING ERRCODE = 'foreign_key_violation';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER check_identifier_entity_exists
          BEFORE INSERT OR UPDATE ON identifiers
          FOR EACH ROW EXECUTE FUNCTION trg_verify_identifier_entity()
        """
    )

    # Reverse protection: identified master data cannot be deleted, so identifiers never
    # point at a row that no longer exists.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_block_delete_if_identified()
        RETURNS TRIGGER AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM identifiers WHERE entity_type = TG_ARGV[0] AND entity_id = OLD.id
          ) THEN
            RAISE EXCEPTION '% % is referenced by identifiers', TG_ARGV[0], OLD.id
              USING ERRCODE = 'foreign_key_violation';
          END IF;
          RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for entity_type, table in ENTITY_TABLES.items():
        op.execute(
            f"""
            CREATE TRIGGER {table}_block_delete_if_identified
              BEFORE DELETE ON {table}
              FOR EACH ROW EXECUTE FUNCTION trg_block_delete_if_identified('{entity_type}')
            """
        )


def downgrade() -> None:
    for table in ENTITY_TABLES.values():
        op.execute(f"DROP TRIGGER {table}_block_delete_if_identified ON {table}")
    op.execute("DROP FUNCTION trg_block_delete_if_identified()")
    op.execute("DROP TABLE identifiers")  # also drops its trigger
    op.execute("DROP FUNCTION trg_verify_identifier_entity()")
