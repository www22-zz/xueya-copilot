"""CLI for the one-time practice data cleanup (PRD 14). See backend/xueya/practice_cleanup.py.

    python -m scripts.cleanup_practice_migration --data-dir .xueya-data --confirm
    python -m scripts.cleanup_practice_migration --data-dir .xueya-data --dry-run
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='.xueya-data')
    parser.add_argument('--confirm', action='store_true',
                        help='required: acknowledge this deletes data and writes no backup')
    parser.add_argument('--dry-run', action='store_true', help='report counts and change nothing')
    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        print('refusing: pass --confirm to delete without a backup, or --dry-run to preview')
        return 2

    db_path = Path(args.data_dir) / 'workspace.sqlite'
    if not db_path.exists():
        print('nothing to clean:', db_path, 'does not exist')
        return 0

    from backend.xueya.database import Database
    from backend.xueya.repository import Repository
    from backend.xueya.practice_cleanup import already_done, cleanup, mark_done

    db = Database(db_path)
    try:
        if already_done(db):
            print('already cleaned once; refusing to run again (PRD 14: 一次性操作)')
            return 0
        counts = cleanup(db, Repository(db), dry_run=args.dry_run)
        print('cleanup counts:', json.dumps(counts, ensure_ascii=False))
        if args.dry_run:
            print('dry run: nothing changed')
        else:
            mark_done(db, counts)
            print('marked done')
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
