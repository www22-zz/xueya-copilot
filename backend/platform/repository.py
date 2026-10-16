import base64
import json
import re
import uuid
from ..core import require, clone, dumps, fingerprint, now_iso, valid_date
from ..rag import catalog

KINDS = {'document', 'source', 'note', 'question', 'attempt', 'event', 'concept', 'plan', 'review', 'session', 'run', 'checkpoint', 'artifact', 'vector'}


def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[\w.:-]{1,150}', value))


def validate_workspace(value):
    require(isinstance(value, dict) and value.get('version') == 3 and valid_id(value.get('activeId')) and isinstance(value.get('courses'), list) and 1 <= len(value['courses']) <= 100, 'INVALID_WORKSPACE')
    ids = set()
    for course in value['courses']:
        require(valid_id(course.get('id')) and course['id'] not in ids and isinstance(course.get('name'), str) and 0 < len(course['name']) <= 100 and isinstance(course.get('data'), dict), 'INVALID_WORKSPACE')
        ids.add(course['id'])
    require(any(c['id'] == value['activeId'] and not c.get('archived') for c in value['courses']), 'ACTIVE_COURSE_REQUIRED')
    return clone(value)


class Repository:
    def __init__(self, db):
        self.db = db

    def require_course(self, scope, allow_archived=False):
        require(isinstance(scope, dict) and set(scope) == {'userId', 'courseId'} and all(valid_id(v) for v in scope.values()), 'INVALID_SCOPE')
        row = self.db.one('SELECT * FROM courses WHERE user_id=? AND id=?', (scope['userId'], scope['courseId']))
        require(row, 'COURSE_NOT_FOUND')
        require(allow_archived or not row['archived'], 'COURSE_ARCHIVED')
        return dict(row)

    def ensure_course(self, user, course):
        require(valid_id(user) and valid_id(course.get('id')), 'INVALID_COURSE')
        self.db.execute('INSERT INTO courses(user_id,id,name,archived) VALUES(?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET name=excluded.name,archived=excluded.archived,version=courses.version+1', (user, course['id'], str(course['name'])[:100], int(bool(course.get('archived')))))

    def courses(self, user):
        return [{**dict(r), 'archived': bool(r['archived'])} for r in self.db.all('SELECT id,name,archived,version FROM courses WHERE user_id=? ORDER BY id', (user,))]

    def read(self, scope, kind, key, include_deleted=False):
        self.require_course(scope, True)
        row = self.db.one('SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND id=?', (scope['userId'], scope['courseId'], kind, key))
        if row and (not row['deleted'] or include_deleted):
            return {'id': row['id'], 'version': row['version'], 'value': json.loads(row['data']), 'createdAt': row['created_at'], 'updatedAt': row['updated_at'], 'deleted': bool(row['deleted'])}

    def put(self, scope, kind, key, value, expected_version=None, deleted=False):
        require(kind in KINDS and valid_id(key), 'INVALID_ENTITY')
        with self.db.transaction():
            self.require_course(scope)
            old = self.read(scope, kind, key, True)
            require(expected_version is None or (old['version'] if old else 0) == expected_version, 'VERSION_CONFLICT')
            at, version, data = now_iso(), (old['version'] if old else 0)+1, dumps(value)
            require(len(data.encode()) <= 16000000, 'ENTITY_TOO_LARGE')
            self.db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,course_id,kind,id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=excluded.updated_at,deleted=excluded.deleted', (scope['userId'], scope['courseId'], kind, key, version, data, old['createdAt'] if old else at, at, int(deleted)))
            self.db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)', (scope['userId'], scope['courseId'], kind, key, version, data, at))
            return {'version': version, 'value': clone(value)}

    def all(self, scope, kind):
        self.require_course(scope, True)
        return [{'id': r['id'], **json.loads(r['data']), 'version': r['version']} for r in self.db.all('SELECT * FROM entities WHERE user_id=? AND course_id=? AND kind=? AND deleted=0 ORDER BY id', (scope['userId'], scope['courseId'], kind))]

    def page(self, scope, kind, cursor=None, limit=20, items=None, label=None):
        require(kind in KINDS, 'INVALID_KIND')
        binding = fingerprint({'scope': scope, 'label': label or kind})
        after = ''
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor+'='*((-len(cursor)) % 4)))
                require(value['binding'] == binding and isinstance(value['after'], str), 'INVALID_CURSOR')
                after = value['after']
            except (ValueError, KeyError):
                require(False, 'INVALID_CURSOR')
        limit = max(1, min(50, int(limit or 20)))
        selected = sorted([v for v in (self.all(scope, kind) if items is None else items) if str(v['id']) > after], key=lambda v: str(v['id']))
        rows = selected[:limit]
        next_cursor = base64.urlsafe_b64encode(dumps({'binding': binding, 'after': rows[-1]['id']}).encode()).decode().rstrip('=') if len(selected) > limit else None
        return {'items': rows, 'nextCursor': next_cursor}

    def get_workspace(self, user):
        row = self.db.one('SELECT * FROM workspaces WHERE user_id=?', (user,))
        return {'version': row['version'], 'data': json.loads(row['data']), 'updatedAt': row['updated_at']} if row else None

    def save_workspace(self, user, value, expected_version=0):
        value = validate_workspace(value)
        with self.db.transaction():
            old = self.get_workspace(user)
            require((old['version'] if old else 0) == expected_version, 'VERSION_CONFLICT')
            for course in value['courses']:
                self.ensure_course(user, {**course, 'archived': False})
                scope, data = {'userId': user, 'courseId': course['id']}, course['data']
                fixture = catalog() if course['id'] == 'course-default' else {'sources': [], 'questions': []}
                groups = {'source': fixture['sources']+[s for d in data.get('documents', []) if not d.get('superseded') and not d.get('deleted') for s in d.get('chunks', [])],
                          'note': [{**n, 'content': n.get('content', n.get('text'))} for n in data.get('cards', [])], 'question': fixture['questions']+data.get('bank', []),
                          'attempt': data.get('records', []), 'plan': [{**d, 'id': d.get('id', 'day-'+str(i))} for i, d in enumerate(data.get('plan', []))], 'session': data.get('sessions', []), 'event': data.get('reviewLog', [])}
                for kind, items in groups.items():
                    seen = set()
                    for index, item in enumerate(items):
                        if not isinstance(item, dict):
                            continue
                        key = str(item.get('id') or kind+'-'+fingerprint(item)[:30]+'-'+str(index))
                        seen.add(key)
                        current = self.read(scope, kind, key)
                        if not current or fingerprint(current['value']) != fingerprint(item):
                            self.put(scope, kind, key, item)
                    for previous in self.all(scope, kind):
                        if previous['id'] not in seen:
                            self.put(scope, kind, previous['id'], previous, deleted=True)
                for document in data.get('documents', []):
                    if document.get('id') and not document.get('remote'):
                        old_doc = self.read(scope, 'document', document['id'])
                        merged = {**(old_doc['value'] if old_doc else {}), **document}
                        if old_doc and old_doc['value'].get('fileHash'):
                            merged.update(fileHash=old_doc['value']['fileHash'], originalAvailable=True)
                        if not old_doc or fingerprint(old_doc['value']) != fingerprint(merged):
                            self.put(scope, 'document', document['id'], merged)
                self.ensure_course(user, course)
            version = expected_version+1
            self.db.execute('INSERT INTO workspaces VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=excluded.updated_at', (user, version, dumps(value), now_iso()))
            return {'version': version, 'data': value}

    def read_source(self, scope, key):
        row = self.read(scope, 'source', key)
        return {'id': key, **row['value'], 'version': row['version']} if row else None

    def apply_confirmed(self, action):
        scope = action['scope']
        with self.db.transaction():
            self.require_course(scope)
            old = self.db.one('SELECT receipt FROM receipts WHERE user_id=? AND course_id=? AND action_id=?', (scope['userId'], scope['courseId'], action['actionId']))
            if old:
                return json.loads(old['receipt'])
            for ref in action['references']:
                source = self.read_source(scope, ref['sourceId'])
                require(source and source['version'] == ref['version'] and fingerprint(source['quote']) == ref['quoteHash'], 'SOURCE_VERSION_CONFLICT')
            saved = self.put(scope, action['kind'], action['entityId'], action['after'], action['expectedVersion'])
            audit = str(uuid.uuid4())
            self.db.execute('INSERT INTO audits VALUES(?,?,?,?,?,?)', (audit, scope['userId'], scope['courseId'], action['actionId'], dumps(action['audit']), now_iso()))
            receipt = {'actionId': action['actionId'], 'version': saved['version'], 'auditId': audit}
            self.db.execute('INSERT INTO receipts VALUES(?,?,?,?)', (scope['userId'], scope['courseId'], action['actionId'], dumps(receipt)))
            workspace = self.get_workspace(scope['userId'])
            if workspace:
                course = next((c for c in workspace['data']['courses'] if c['id'] == scope['courseId']), None)
                if course:
                    data, value = course['data'], action['after']
                    if action['kind'] == 'plan':
                        data['plan'] = [{**day, 'id': action['entityId']+'-day-'+str(i), 'tasks': [{**task, 'id': action['entityId']+'-task-'+str(i)+'-'+str(j)} for j, task in enumerate(day['tasks'])]} for i, day in enumerate(value['days'])]
                        data['planVersion'] = data.get('planVersion', 0)+1
                    else:
                        field = 'cards' if action['kind'] == 'note' else 'bank'
                        item = {**value, 'id': action['entityId'], 'createdAt': now_iso()}
                        if field == 'cards':
                            item.update(text=value['content'], sources=[self.read_source(scope, key) for key in value.get('sourceIds', [])])
                        else:
                            item.update(type='short', answerText=value['answer'], sourceId=value['sourceIds'][0], topic='课程练习', version=1)
                        data[field] = [item]+[i for i in data.get(field, []) if i['id'] != item['id']]
                    self.db.execute('UPDATE workspaces SET version=version+1,data=?,updated_at=? WHERE user_id=?', (dumps(workspace['data']), now_iso(), scope['userId']))
            return receipt
