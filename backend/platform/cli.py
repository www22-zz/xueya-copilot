import argparse
import json
import os
import subprocess
import sys
import httpx
from ..config import load_config, ROOT
from ..core import require
from . import Platform
from .backup import create_backup, restore_backup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['doctor', 'start', 'stop', 'init', 'backup', 'restore', 'export', 'gc'], default='doctor', nargs='?')
    parser.add_argument('argument', nargs='?')
    parser.add_argument('target', nargs='?')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = load_config()
    directory = config['platform']['dataDir']
    if args.command == 'doctor':
        import sqlite3
        print(json.dumps({'python': sys.version.split()[0], 'pythonSupported': sys.version_info >= (3, 12), 'sqlite': sqlite3.sqlite_version, 'dataDir': str(directory), 'model': config['ai']['model'], 'apiConfigured': bool(config['ai']['apiKey']), 'inference': 'external-api-only', 'gpuRequired': False, 'nodeRequired': False}, indent=2))
        return
    if args.command == 'start':
        directory.mkdir(parents=True, exist_ok=True)
        log = ROOT/'test-results'
        log.mkdir(exist_ok=True)
        with (log/'python-server.stdout.log').open('a', encoding='utf-8') as stdout, (log/'python-server.stderr.log').open('a', encoding='utf-8') as stderr:
            process = subprocess.Popen([sys.executable, '-m', 'backend.server'], cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, start_new_session=os.name != 'nt')
        print('Python server launched; PID '+str(process.pid))
        return
    if args.command == 'stop':
        pid_file = directory/'server.json'
        require(pid_file.exists(), 'SERVER_PID_NOT_FOUND')
        identity = json.loads(pid_file.read_text(encoding='utf-8'))
        base = 'http://127.0.0.1:'+str(identity['port'])
        require(httpx.get(base+'/api/health', timeout=2).json().get('instanceId') == identity['instanceId'], 'SERVER_IDENTITY_MISMATCH')
        require(httpx.post(base+'/api/platform/shutdown', headers={'X-Xueya-Stop': identity['stopToken']}, timeout=3).is_success, 'STOP_REJECTED')
        print('Requested safe shutdown.')
        return
    if args.command == 'restore':
        require(args.argument and args.target, 'RESTORE_SOURCE_AND_NEW_DIRECTORY_REQUIRED')
        print(json.dumps(restore_backup(args.argument, args.target)))
        return
    platform = Platform(directory, recover=False)
    try:
        if args.command == 'init':
            result = {'ok': True, 'dataDir': str(directory), 'courses': platform.repository.courses(platform.user_id)}
        elif args.command == 'backup':
            require(args.argument, 'BACKUP_DESTINATION_REQUIRED')
            result = create_backup(platform, args.argument)
        elif args.command == 'export':
            require(args.argument, 'EXPORT_REQUIRES_NEW_FILE')
            file = ROOT/args.argument
            require(not file.exists(), 'EXPORT_REQUIRES_NEW_FILE')
            with file.open('x', encoding='utf-8') as stream:
                json.dump({'schemaVersion': 1, 'workspace': platform.repository.get_workspace(platform.user_id), 'courses': platform.repository.courses(platform.user_id)}, stream, ensure_ascii=False, indent=2)
            result = {'exported': True}
        else:
            refs = {json.loads(row['data']).get('fileHash') for row in platform.db.all("SELECT data FROM revisions WHERE kind='document'")}
            candidates = [f for f in platform.files.inventory() if f['hash'] not in refs]
            if args.apply:
                for file in candidates:
                    platform.files.remove_unreferenced(file['hash'], refs)
            result = {'dryRun': not args.apply, 'candidates': candidates}
        print(json.dumps(result, ensure_ascii=True))
    finally:
        platform.db.close()


if __name__ == '__main__':
    main()
