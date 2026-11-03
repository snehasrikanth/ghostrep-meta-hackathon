"""Demo athlete commands.

  cd backend && uv run python -m app.demo seed --dry-run
  cd backend && uv run python -m app.demo seed
  cd backend && uv run python -m app.demo seed --refresh
  cd backend && uv run python -m app.demo cleanup --dry-run
  cd backend && uv run python -m app.demo cleanup

Dates are the athlete's local calendar. Stored timestamps are UTC.
Default timezone is the host's local zone. Pass --timezone America/New_York
to pin it. This command never calls Muse or SAM and never runs at startup.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.services.demo.seed import DemoBusyError, cleanup_demo, seed_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or remove the isolated GhostRep demo athlete.")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Create the demo athlete if missing. Refuses to clobber later demo edits.")
    seed.add_argument("--dry-run", action="store_true", help="Show intended changes without writing.")
    seed.add_argument("--refresh", action="store_true", help="Replace only the demo athlete, including later demo-only edits.")
    seed.add_argument("--anchor", help="Local calendar date YYYY-MM-DD. Defaults to today in --timezone.")
    seed.add_argument("--timezone", help="IANA timezone for calendar days. Defaults to the host local zone.")

    clean = sub.add_parser("cleanup", help="Delete only the demo athlete and demo-owned records.")
    clean.add_argument("--dry-run", action="store_true", help="Show what would be removed without writing.")

    args = parser.parse_args(argv)
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    db = SessionLocal()
    try:
        if args.command == "cleanup":
            result = cleanup_demo(db, dry_run=args.dry_run)
            print(result.as_text())
            return 0
        anchor = date.fromisoformat(args.anchor) if args.anchor else None
        result = seed_demo(
            db,
            anchor=anchor,
            timezone_name=args.timezone,
            refresh=args.refresh,
            dry_run=args.dry_run,
        )
        print(result.as_text())
        return 0
    except DemoBusyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
