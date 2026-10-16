import json
import time
import uuid
import hashlib
from ..core import require, clone, dumps, now_iso, valid_date, check_cancel
from ..platform.repository import valid_id


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class ActionAuthority:
    def __init__(self, repository, ttl_ms=300000, now=lambda: int(time.time()*1000), recover=True):
        self.repository, self.db, self.ttl, self.now = repository, repository.db, ttl_ms, now
        if recover:
            for row in self.db.all('SELECT * FROM confirmations'):
                action = json.loads(row['data'])
                if action['state'] in ('executing', 'uncertain'):
                    receipt = self.db.one('SELECT receipt FROM receipts WHERE user_id=? AND course_id=? AND action_id=?', (action['scope']['userId'], action['scope']['courseId'], row['id']))
                    action['state'] = 'applied' if receipt else 'uncertain'
                    if receipt:
                        action['receipt'] = json.loads(receipt['receipt'])
                    self._save(action)

    def _save(self, action):
        self.db.execute('INSERT INTO confirmations VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (action['actionId'], dumps(action)))

    def _get(self, scope, key, live=False):
        self.repository.require_course(scope)
        row = self.db.one('SELECT data FROM confirmations WHERE id=?', (key,))
        action = json.loads(row['data']) if row else None
        require(action and action['scope'] == scope, 'ACTION_NOT_FOUND')
        if live:
            require(action['expiresAt'] > self.now(), 'ACTION_EXPIRED')
            require(action['state'] in ('preview', 'confirmed'), 'ACTION_NOT_PENDING')
        return action

    async def prepare(self, scope, value, signal=None):
        self.repository.require_course(scope)
        require(set(value) == {'kind', 'entityId', 'expectedVersion', 'after'} and value['kind'] in ('note', 'question', 'plan') and valid_id(value['entityId']) and type(value['expectedVersion']) is int and value['expectedVersion'] >= 0, 'INVALID_ACTION')
        after, kind = clone(value['after']), value['kind']
        require(isinstance(after, dict), 'INVALID_ACTION')
        if kind == 'note':
            require(set(after) <= {'title', 'content', 'sourceIds'} and isinstance(after.get('title'), str) and 0 < len(after['title']) <= 200 and isinstance(after.get('content'), str) and len(after['content']) <= 30000, 'INVALID_ACTION')
            after.setdefault('sourceIds', [])
        elif kind == 'question':
            require(set(after) == {'prompt', 'answer', 'sourceIds'} and isinstance(after['prompt'], str) and 0 < len(after['prompt']) <= 5000 and isinstance(after['answer'], str) and 0 < len(after['answer']) <= 10000 and after['sourceIds'], 'INVALID_ACTION')
        else:
            require(set(after) == {'title', 'days'} and isinstance(after['title'], str) and 0 < len(after['title']) <= 200 and isinstance(after['days'], list) and len(after['days']) <= 90, 'INVALID_ACTION')
            for day in after['days']:
                require(set(day) == {'date', 'tasks'} and valid_date(day['date']) and isinstance(day['tasks'], list) and len(day['tasks']) <= 30 and all(set(t) == {'title', 'minutes'} and isinstance(t['title'], str) and 0 < len(t['title']) <= 300 and type(t['minutes']) is int and 1 <= t['minutes'] <= 480 for t in day['tasks']), 'INVALID_ACTION')
        refs = after.get('sourceIds', [])
        require(isinstance(refs, list) and len(refs) <= (30 if kind == 'question' else 100) and all(valid_id(key) for key in refs) and len(dumps(after).encode()) <= 48000, 'ACTION_TOO_LARGE')
        for row in self.db.all('SELECT * FROM confirmations'):
            previous = json.loads(row['data'])
            if previous['expiresAt'] <= self.now() and previous['state'] not in ('executing', 'uncertain'):
                self.db.execute('DELETE FROM confirmations WHERE id=?', (row['id'],))
        require(self.db.one('SELECT COUNT(*) AS n FROM confirmations')['n'] < 100, 'ACTION_CAPACITY')
        check_cancel(signal)
        current = self.repository.read(scope, kind, value['entityId'])
        require((current['version'] if current else 0) == value['expectedVersion'], 'VERSION_CONFLICT')
        references = []
        for key in refs:
            source = self.repository.read_source(scope, key)
            require(source, 'SOURCE_NOT_FOUND')
            # Repository uses the same ordinary JSON string hash as the original implementation.
            from ..core import fingerprint
            references.append({'sourceId': key, 'version': source['version'], 'quoteHash': fingerprint(source['quote'])})
        preview = {'actionId': str(uuid.uuid4()), 'scope': clone(scope), 'kind': kind, 'entityId': value['entityId'], 'expectedVersion': value['expectedVersion'], 'before': current['value'] if current else None, 'after': after, 'references': references, 'expiresAt': self.now()+self.ttl}
        preview['digest'] = digest(preview)
        self._save({**preview, 'state': 'preview'})
        return preview

    def preview(self, scope, key):
        return {k: v for k, v in self._get(scope, key, True).items() if k != 'state'}

    def confirm(self, scope, value):
        action = self._get(scope, value.get('actionId'), True)
        require(action['state'] == 'preview', 'ACTION_ALREADY_CONFIRMED')
        require(action['digest'] == value.get('digest'), 'ACTION_CHANGED')
        action['state'] = 'confirmed'
        self._save(action)
        return {'actionId': action['actionId'], 'state': 'confirmed'}

    def cancel(self, scope, key):
        action = self._get(scope, key, True)
        action['state'] = 'cancelled'
        self._save(action)
        return {'actionId': key, 'state': 'cancelled'}

    async def apply(self, scope, key, signal=None):
        action = self._get(scope, key)
        if action['state'] == 'applied':
            return clone(action['receipt'])
        self._get(scope, key, True)
        require(action['state'] == 'confirmed', 'ACTION_CONFIRMATION_REQUIRED')
        check_cancel(signal)
        action['state'] = 'executing'
        self._save(action)
        try:
            receipt = self.repository.apply_confirmed({**action, 'audit': {'actionId': key, 'digest': action['digest'], 'actor': scope['userId'], 'courseId': scope['courseId'], 'kind': action['kind'], 'entityId': action['entityId'], 'at': now_iso()}})
            require(receipt.get('actionId') == key and receipt.get('version') == action['expectedVersion']+1 and receipt.get('auditId'), 'INVALID_WRITE_RECEIPT')
            action.update(state='applied', receipt=receipt)
            self._save(action)
            return clone(receipt)
        except BaseException:
            action['state'] = 'uncertain'
            self._save(action)
            raise
