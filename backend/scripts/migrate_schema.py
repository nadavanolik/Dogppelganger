#!/usr/bin/env python
"""Bring an existing database up to the current models. Run before deploying.

    python scripts/migrate_schema.py            # apply
    python scripts/migrate_schema.py --dry-run  # just say what would happen

**Why this exists.** ``main.py`` calls ``Base.metadata.create_all()``, which
creates *missing tables* and nothing else — it will not add a column to a table
that already exists. The Postgres data directory is a named volume
(``dbdata``), so it survives every deploy. Without this script, a VM that has
already run the old code keeps an ``upload_jobs`` table with
``breed_name``/``trait``/``confidence`` and none of the new columns, and every
query SQLAlchemy emits against the new mapping fails with UndefinedColumn —
uploads, the forum feed and the match endpoints all 500 at once.

Idempotent: it inspects the live schema and only issues the changes that are
actually missing, so running it twice, or on a fresh database, is a no-op.

This is deliberately not Alembic. One schema change, two tables, no branching
history — a migration framework would be more machinery than the problem has.
If the schema starts changing regularly, switch to Alembic rather than growing
this file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect, text  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app import models  # noqa: F401,E402  (registers the tables on Base)

# Column types are spelled in SQL that both Postgres and SQLite accept.
# SQLite is permissive about type names; Postgres is the one that matters.
ADDED: dict[str, list[tuple[str, str]]] = {
    "upload_jobs": [
        ("checksum", "VARCHAR(64)"),
        ("byte_size", "INTEGER"),
        ("width", "INTEGER"),
        ("height", "INTEGER"),
        ("dog_asset_id", "INTEGER"),
        ("score", "FLOAT"),
        ("shared_traits", "JSON"),
    ],
    "matches": [
        ("dog_asset_id", "INTEGER"),
        ("score", "FLOAT"),
        ("shared_traits", "JSON"),
    ],
}

# The invented-breed columns. `matches.breed_name` was NOT NULL, so leaving it
# in place would fail every INSERT the new code makes, not just the SELECTs.
DROPPED: dict[str, list[str]] = {
    "upload_jobs": ["breed_name", "trait", "confidence"],
    "matches": ["breed_name", "trait", "confidence"],
}

# (index name, columns). Every worker polls `WHERE status = 'queued'` on
# every claim (app/uploads/queue.py) — on a VM that has been running a while,
# that must stay a lookup, not a scan over every job ever finished.
ADDED_INDEXES: dict[str, list[tuple[str, list[str]]]] = {
    "upload_jobs": [("ix_upload_jobs_status", ["status"])],
}


def plan(connection) -> list[str]:
    """The DDL this database still needs, in the order it must be applied."""
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    statements: list[str] = []

    for table, columns in ADDED.items():
        if table not in existing_tables:
            continue  # create_all() will build it complete
        present = {c["name"] for c in inspector.get_columns(table)}
        for name, sql_type in columns:
            if name not in present:
                statements.append(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")

    for table, columns in DROPPED.items():
        if table not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table)}
        for name in columns:
            if name in present:
                statements.append(f"ALTER TABLE {table} DROP COLUMN {name}")

    for table, indexes in ADDED_INDEXES.items():
        if table not in existing_tables:
            continue
        present = {ix["name"] for ix in inspector.get_indexes(table)}
        for name, columns in indexes:
            if name not in present:
                statements.append(f"CREATE INDEX {name} ON {table} ({', '.join(columns)})")

    return statements


def migrate(dry_run: bool = False) -> list[str]:
    # First, so a database that predates dog_assets gets the table before
    # anything tries to reference it.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        statements = plan(connection)
        if dry_run:
            return statements
        for statement in statements:
            print(f"  {statement}")
            connection.execute(text(statement))
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    args = parser.parse_args()

    statements = migrate(dry_run=args.dry_run)
    if not statements:
        print("schema is already up to date — nothing to do")
        return 0

    verb = "would apply" if args.dry_run else "applied"
    print(f"{verb} {len(statements)} change(s)")
    if args.dry_run:
        for statement in statements:
            print(f"  {statement}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
