import json
import time
import uuid
from ..core import require, clone, fingerprint, now_iso, dumps
from .repository import validate_workspace


class BrowserMigration:
    def __init__(self, repository, now=lambda: int(time.time()*1000)):
        self.repository, self.now, self.previews = repository, now, {}

    def preview(self, user, value):
        workspace, raw = validate_workspace(value['workspace']), value.get('raw', {})
        require(len(dumps({'workspace': workspace, 'raw': raw}).encode()) <= 24000000, 'IMPORT_TOO_LARGE')
        digest = fingerprint({'workspace': workspace, 'raw': raw})
        old = self.repository.db.one('SELECT * FROM imports WHERE user_id=? AND hash=?', (user, digest))
        self.previews = {key: p for key, p in self.previews.items() if p['expiresAt'] > self.now()}
        require(len(self.previews) < 20, 'IMPORT_CAPACITY')
        counts = {'courses': len(workspace['courses']), 'documents': 0, 'messages': 0, 'records': 0, 'cards': 0}
        for course in workspace['courses']:
            data = course['data']
            for key in ('documents', 'records', 'cards'):
                counts[key] += len(data.get(key, []))
            counts['messages'] += max(len(data.get('messages', [])), sum(len(s.get('messages', [])) for s in data.get('sessions', [])))
        stored = self.repository.get_workspace(user)
        preview = {'id': str(uuid.uuid4()), 'hash': digest, 'counts': counts, 'expectedVersion': stored['version'] if stored else 0, 'expiresAt': self.now()+300000, 'alreadyImported': bool(old)}
        self.previews[preview['id']] = {**preview, 'userId': user, 'workspace': workspace, 'raw': raw}
        return preview

    def apply(self, user, value):
        preview = self.previews.get(value.get('id'))
        require(preview and preview['userId'] == user, 'IMPORT_NOT_FOUND')
        require(preview['expiresAt'] > self.now(), 'IMPORT_EXPIRED')
        require(preview['hash'] == value.get('hash'), 'IMPORT_CHANGED')
        old = self.repository.db.one('SELECT * FROM imports WHERE user_id=? AND hash=?', (user, preview['hash']))
        if old:
            return {'alreadyImported': True, 'version': old['workspace_version'], 'counts': preview['counts']}
        with self.repository.db.transaction():
            previous = self.repository.get_workspace(user)
            saved = self.repository.save_workspace(user, preview['workspace'], preview['expectedVersion'])
            self.repository.db.execute('INSERT INTO imports VALUES(?,?,?,?,?)', (user, preview['hash'], dumps({'raw': preview['raw'], 'workspace': preview['workspace'], 'previous': previous}), saved['version'], now_iso()))
            return {'version': saved['version'], 'counts': preview['counts'], 'backupId': preview['hash']}

    def backup(self, user, key):
        row = self.repository.db.one('SELECT backup FROM imports WHERE user_id=? AND hash=?', (user, key))
        require(row, 'IMPORT_NOT_FOUND')
        return json.loads(row['backup'])
