#!/usr/bin/env python
"""Wipe the database and every file that references a row in it.

    ALLOW_DB_RESET=1 python scripts/reset_db.py --yes

Why this exists rather than a migration: making users real turns
``upload_jobs.owner_id`` (and three more columns) from ``VARCHAR(64)`` holding
strings like ``"u_moodyoak"`` into ``INTEGER REFERENCES users(id)``. There is no
``USING`` expression that turns a browser-invented label into a user id, so
``scripts/migrate_schema.py`` cannot express this change and no amount of
growing it would help. The data is a handful of test uploads on a school
project, so the honest move is to start clean.

**This is destructive and irreversible.** It therefore requires two independent
confirmations — ``--yes`` on the command line *and* ``ALLOW_DB_RESET=1`` in the
environment — so that neither a stray shell-history recall nor a copied CI step
can trigger it alone. It is deliberately not wired into deploy.yml: a
destructive step must never run on every push.

**What it does NOT touch: the dog corpus — neither the files nor the rows.**
``dog_assets`` and ``calibrations`` hold no user data. They are derived from a
public dataset by three offline passes that together take hours, and
``ingest_dogs.py`` requires ``--source`` pointing at the 700MB AFHQ archive,
which is not kept on the VM. Dropping them to delete somebody's photos would be
a wildly disproportionate trade. Pass ``--include-corpus`` if you really do want
a bare database.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app import models  # noqa: F401,E402  (import so tables register on Base)
from app.game import store  # noqa: E402
from app.storage import layout  # noqa: E402


# Tables that describe the public dog corpus rather than any person. Rebuilding
# them means the AFHQ archive plus the embedding and calibration passes, so they
# survive a reset by default — see the module docstring.
CORPUS_TABLES = frozenset({"dog_assets", "calibrations"})


def tables_to_drop(include_corpus: bool = False) -> list:
    """Which tables a reset would drop, in dependency-safe order.

    Split out so it can be asserted on without running anything destructive.
    """
    tables = list(Base.metadata.sorted_tables)
    if include_corpus:
        return tables
    return [t for t in tables if t.name not in CORPUS_TABLES]


def _rmtree(path: Path) -> int:
    """Delete a directory tree, reporting how many files went with it."""
    if not path.exists():
        return 0
    count = sum(1 for p in path.rglob("*") if p.is_file())
    shutil.rmtree(path, ignore_errors=True)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--yes", action="store_true", help="confirm the wipe")
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would go, change nothing"
    )
    parser.add_argument(
        "--include-corpus",
        action="store_true",
        help="also drop dog_assets and calibrations (needs a full re-ingest afterwards)",
    )
    args = parser.parse_args()

    upload_root = layout.upload_root()
    doomed = tables_to_drop(args.include_corpus)

    print("This will permanently delete:")
    print(f"  - tables     {', '.join(sorted(t.name for t in doomed))}")
    print(f"  - database   {settings.DATABASE_URL}")
    print(f"  - uploads    {upload_root}")
    print(f"  - attachments {layout.attachment_root()}")
    print(f"  - leaderboard {store.DATA_FILE}")
    if args.include_corpus:
        print("\n  !! --include-corpus: the dog corpus rows go too. Rebuilding them")
        print("     needs the AFHQ archive and the embedding + calibration passes.")
    else:
        print(
            f"\nLeaving alone: the dog corpus - files at {layout.dog_root()}, and the\n"
            f"  {', '.join(sorted(CORPUS_TABLES))} rows that describe them."
        )

    if args.dry_run:
        print("\n--dry-run: nothing changed.")
        return 0

    if not args.yes or os.getenv("ALLOW_DB_RESET") != "1":
        print(
            "\nRefusing to run. This needs BOTH confirmations:\n"
            "    ALLOW_DB_RESET=1 python scripts/reset_db.py --yes",
            file=sys.stderr,
        )
        return 2

    print(f"\ndropping {len(doomed)} table(s)...")
    Base.metadata.drop_all(bind=engine, tables=doomed)
    print("recreating them from the models...")
    Base.metadata.create_all(bind=engine)

    removed = _rmtree(upload_root)
    print(f"removed {removed} upload file(s) from {upload_root}")

    removed = _rmtree(layout.attachment_root())
    print(f"removed {removed} attachment file(s) from {layout.attachment_root()}")

    if store.DATA_FILE.exists():
        # Keyed by arbitrary strings ("p_a", "u_moodyoak") that no longer
        # correspond to anyone, so the scores are not salvageable.
        store.DATA_FILE.unlink()
        print(f"removed {store.DATA_FILE}")

    print("\ndone - the database is consistent with the current models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
