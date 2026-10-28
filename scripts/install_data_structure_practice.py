"""Preview/apply the rebuilt curriculum to one existing textbook course. No model calls."""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.xueya.platform import Platform
from backend.xueya.rag_service import RagService
from backend.xueya.curated_practice import CuratedPractice


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path('.xueya-data'))
    parser.add_argument('--course-id', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    require_file = args.data_dir/'workspace.sqlite'
    if not require_file.is_file():
        raise SystemExit('EXISTING_DATABASE_REQUIRED')
    host = Platform(args.data_dir, recover=False, preserve_legacy_data=True)
    try:
        scope = host.scope(args.course_id)
        service = CuratedPractice(host, RagService(host))
        if args.apply:
            backup_dir = args.data_dir.parent/'.xueya-backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir/('before-curated-practice-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite')
            with sqlite3.connect(backup) as destination:
                host.db.connection.backup(destination)
            before = host.db.one("SELECT COUNT(*) AS n FROM entities WHERE kind IN ('event','attempt','note')")['n']
            result = service.install(scope)
            after = host.db.one("SELECT COUNT(*) AS n FROM entities WHERE kind IN ('event','attempt','note')")['n']
            if before != after:
                raise RuntimeError('PRACTICE_HISTORY_COUNT_CHANGED')
            result.update(backup=str(backup.resolve()), preservedHistoryRecords=after)
        else:
            value = service.preview(scope)
            result = {'packageId':value['packageId'], 'name':value['name'], 'questions':len(value['questions']), 'units':len(value['units'])}
        print(json.dumps({'applied':args.apply, 'courseId':args.course_id, **result}, ensure_ascii=False))
    finally:
        host.db.close()


if __name__ == '__main__':
    main()
