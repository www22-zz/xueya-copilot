"""C async persistence ports backed by E's existing SQLite transactions."""
import json
from ..core import require, clone, dumps, fingerprint


class LearningRepository:
    def __init__(self, platform):
        self.platform, self.repository, self.db = platform, platform.repository, platform.db

    async def get(self, course, key):
        row = self.repository.read(self.platform.scope(course), 'artifact', key)
        return clone(row['value']) if row else None

    async def get_operation(self, course, operation):
        self.platform.scope(course)
        key = 'c:operation:'+fingerprint([self.platform.user_id, course, operation])
        row = self.db.one('SELECT value FROM meta WHERE key=?', (key,))
        return json.loads(row['value']) if row else None

    async def commit(self, value):
        scope = self.platform.scope(value['courseId'])
        with self.db.transaction():
            key = 'c:operation:'+fingerprint([scope['userId'], scope['courseId'], value['operationId']])
            previous = self.db.one('SELECT value FROM meta WHERE key=?', (key,))
            if previous:
                old = json.loads(previous['value'])
                require(old['requestHash'] == value['requestHash'], 'IDEMPOTENCY_CONFLICT')
                return old['value']
            current = self.repository.read(scope, 'artifact', value['id'])
            require((current['value']['revision'] if current else 0) == value['expectedRevision'], 'ARTIFACT_CONFLICT')
            self.repository.put(scope, 'artifact', value['id'], value['value'], current['version'] if current else 0)
            self.db.execute('INSERT INTO meta VALUES(?,?)', (key, dumps({'requestHash': value['requestHash'], 'value': value['value']})))
            return clone(value['value'])

    async def compare_and_set(self, course, key, revision, value):
        scope = self.platform.scope(course)
        with self.db.transaction():
            current = self.repository.read(scope, 'artifact', key)
            if (current['value']['revision'] if current else 0) != revision:
                return False
            self.repository.put(scope, 'artifact', key, value, current['version'] if current else 0)
            return True
