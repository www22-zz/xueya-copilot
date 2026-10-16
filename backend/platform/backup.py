import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid
from ..core import require, now_iso


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_backup(platform, destination):
    destination = Path(destination).resolve()
    require(not destination.exists(), 'BACKUP_DESTINATION_EXISTS')
    destination.mkdir(parents=True)
    target = sqlite3.connect(destination/'workspace.sqlite')
    try:
        platform.db.connection.backup(target)
    finally:
        target.close()
    entries = [{'path': 'workspace.sqlite', 'sha256': checksum(destination/'workspace.sqlite')}]
    for file in platform.files.inventory():
        relative = 'files/'+file['hash'][:2]+'/'+file['hash']
        path = destination/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(platform.files.read(file['hash']))
        entries.append({'path': relative, 'sha256': checksum(path)})
    (destination/'manifest.json').write_text(json.dumps({'version': 1, 'createdAt': now_iso(), 'entries': entries}, indent=2), encoding='utf-8')
    return {'destination': str(destination), 'files': len(entries)}


def restore_backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    require(not destination.exists(), 'RESTORE_REQUIRES_NEW_DIRECTORY')
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    require(manifest.get('version') == 1 and isinstance(manifest.get('entries'), list) and any(e['path'] == 'workspace.sqlite' for e in manifest['entries']), 'INVALID_BACKUP')
    seen = set()
    for entry in manifest['entries']:
        require(re.fullmatch(r'(workspace\.sqlite|files/[a-f0-9]{2}/[a-f0-9]{64})', entry['path']) and entry['path'] not in seen, 'UNSAFE_BACKUP_PATH')
        file = source/entry['path']
        require(file.resolve().is_relative_to(source) and not file.is_symlink() and not file.parent.is_symlink() and checksum(file) == entry['sha256'], 'BACKUP_CHECKSUM_MISMATCH')
        seen.add(entry['path'])
    probe = sqlite3.connect((source/'workspace.sqlite').as_uri()+'?mode=ro', uri=True)
    try:
        require(probe.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'DATABASE_INTEGRITY_FAILED')
    finally:
        probe.close()
    staging = destination.with_name(destination.name+'.restore-'+str(uuid.uuid4()))
    staging.mkdir(parents=True)
    for entry in manifest['entries']:
        target = staging/entry['path']
        require(target.resolve().is_relative_to(staging.resolve()), 'UNSAFE_BACKUP_PATH')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write((source/entry['path']).read_bytes())
    for attempt in range(6):
        try:
            require(not destination.exists(), 'RESTORE_REQUIRES_NEW_DIRECTORY')
            staging.rename(destination)
            break
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.02*2**attempt)
    return {'destination': str(destination), 'files': len(manifest['entries'])}
