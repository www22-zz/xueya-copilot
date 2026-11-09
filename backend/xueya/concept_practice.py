"""Source-scoped concept exercises; reads never dispatch model work."""
from .common import require, digest

DIFFICULTIES = ('简单', '中等', '困难')


def context(materials, account, owner, course, concept_id):
    scope, documents, ranges = materials.corpus.inventory(account, owner, course)
    for doc in documents:
        if not doc['ready']:continue
        seed = materials.p.repo.read(scope, 'artifact', doc['id'])
        if seed:
            source = next((s for s, d, _ in materials.documents(owner, course).values()
                           if materials.key(s, d) == doc['id']), None)
            raw = next((d for s, d, _ in materials.documents(owner, course).values()
                        if materials.key(s, d) == doc['id']), None)
            ranges.append({'id': doc['id'], 'saved': seed['value'], 'scope': source.wire(),
                           'rawId': raw['id'], 'revision': doc['revision'], 'part': None})
    for item in ranges:
        for node in (item.get('saved') or {}).get('concepts', []):
            if node['id'] == concept_id:
                return scope, item, node
    require(False, 'CONCEPT_NOT_ACCESSIBLE')


def read(materials, account, owner, course, concept_id):
    scope, item, node = context(materials, account, owner, course, concept_id)
    groups = {k: [] for k in (*DIFFICULTIES, '待分级')}
    for qid in node['questionIds']:
        row = materials.p.repo.read(scope, 'question', qid)
        if not row:
            continue
        q = row['value']
        if q.get('conceptId') != concept_id:
            continue
        groups[q.get('difficulty') if q.get('difficulty') in DIFFICULTIES else '待分级'].append(
            {**materials.service.public_question(q), 'revision': row['version']})
    jobs = []
    for row in materials.p.db.all("SELECT id,input FROM jobs WHERE user_id=? AND type='material-learning'", (scope.user_id,)):
        import json
        args=json.loads(row['input'])
        if args.get('targetConcept')==concept_id:
            jobs.append({**materials.p.jobs.get(row['id'],scope.user_id), 'difficulty':args['difficulty']})
    return {'concept': node, 'groups': groups, 'sourceRevision': item['revision'], 'jobs': jobs}


def supplement(materials, account, owner, course, value):
    require(value.get('confirmedExternal') is True, 'EXTERNAL_CONFIRMATION_REQUIRED')
    difficulty = value.get('difficulty')
    require(difficulty in DIFFICULTIES, 'INVALID_DIFFICULTY')
    scope, item, node = context(materials, account, owner, course, value.get('conceptId'))
    from .common import Scope
    materials.current(owner, course, Scope(**item['scope']), item['rawId'], item['revision'])
    require(bool(materials.app.state.config.api_key), 'AI_UNAVAILABLE')
    key = 'supplement-' + digest([node['id'], item['revision'], difficulty])[:40]
    with materials.p.db.transaction():
        prior = materials.p.db.one('SELECT id FROM jobs WHERE user_id=? AND type=? AND idempotency_key=?',
                                  (scope.user_id, 'material-learning', key))
        if prior:
            return materials.p.jobs.get(prior['id'], scope.user_id)
        return materials.p.jobs.submit(scope.user_id, {'type': 'material-learning', 'courseId': scope.course_id,
            'resource': 'api', 'maxAttempts': 1, 'idempotencyKey': key, 'input': {
                'account': account, 'owner': owner, 'requestCourse': course, 'sourceScope': item['scope'],
                'documentId': item['rawId'], 'revision': item['revision'], 'materialId': item['id'],
                'sourcePart': [p for p in item['part'] if p['sourceId'] in node['sourceIds']] if item['part'] else None, 'targetConcept': node['id'], 'targetLabel': node['label'],
                'targetSourceIds': node['sourceIds'], 'difficulty': difficulty, 'supplementKey': key}})
