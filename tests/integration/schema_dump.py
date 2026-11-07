"""Deterministic text dump of the public schema, used by the migration drift checks (P1-19).

It captures everything the plan says an ORM autogenerate would lose: constraints (including
exclusion constraints), indexes, triggers and function bodies, as PostgreSQL itself prints them.
Objects are sorted by name and nothing machine-specific (oids, timestamps) is included.
"""

from __future__ import annotations

import psycopg

Conn = psycopg.Connection[tuple[object, ...]]


def dump_schema(conn: Conn) -> str:
    lines: list[str] = []
    extensions = conn.execute(
        "SELECT extname FROM pg_extension WHERE extname <> 'plpgsql' ORDER BY extname"
    ).fetchall()
    lines += [f"extension {row[0]}" for row in extensions]

    tables = conn.execute(
        "SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version' "
        "ORDER BY c.relname"
    ).fetchall()
    for oid, name in tables:
        lines.append(f"\ntable {name}")
        columns = conn.execute(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
            "pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum",
            (oid,),
        ).fetchall()
        for col, col_type, not_null, default in columns:
            null = "NOT NULL" if not_null else "NULL"
            default_part = f" DEFAULT {default}" if default is not None else ""
            lines.append(f"  column {col} {col_type} {null}{default_part}")
        for cname, cdef in conn.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s ORDER BY conname",
            (oid,),
        ):
            lines.append(f"  constraint {cname}: {cdef}")
        for iname, idef in conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = %s ORDER BY indexname",
            (name,),
        ):
            lines.append(f"  index {iname}: {idef}")
        for tname, tdef in conn.execute(
            "SELECT tgname, pg_get_triggerdef(oid) FROM pg_trigger "
            "WHERE tgrelid = %s AND NOT tgisinternal ORDER BY tgname",
            (oid,),
        ):
            lines.append(f"  trigger {tname}: {tdef}")

    functions = conn.execute(
        "SELECT p.oid::regprocedure::text, pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.prokind = 'f' "
        "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e') "
        "ORDER BY 1"
    ).fetchall()
    for signature, definition in functions:
        lines.append(f"\nfunction {signature}\n{str(definition).strip()}")
    return "\n".join(lines).strip() + "\n"
