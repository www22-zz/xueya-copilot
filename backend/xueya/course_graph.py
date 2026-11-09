"""Resumable, permission-scoped whole-corpus extraction using the shared jobs.

Input range coverage is measured separately from academic completeness.
Nothing in this service dispatches automatically from a read operation.
"""
import json
import re
import unicodedata
from .common import digest, require

JOB = 'course-graph-range'
SIZE = 1800


def label_key(value):
    return re.sub(r'[\s，,。；;：:、]+', '', unicodedata.normalize('NFKC', value).casefold())


class CourseGraph:
    def __init__(self, materials):
        self.m = materials
        self.p = materials.p
        self.p.jobs.register(JOB, self.execute)

    def inventory(self, account, owner, course, subject=''):
        scope = self.m.service._scope(account)
        documents, ranges, seen = [], [], set()
        parsing = {(r['user_id'], r['course_id'], json.loads(r['input']).get('documentId')) for r in self.p.db.all(
            "SELECT user_id,course_id,input FROM jobs WHERE type='rag-parse' AND status IN ('queued','running')")}
        artifacts = {r['id']: r for r in self.p.repo.all(scope, 'artifact')}
        jobs = {r['idempotency_key']: r for r in self.p.db.all(
            'SELECT id,idempotency_key,status,error FROM jobs WHERE user_id=? AND type=?', (scope.user_id, JOB))}
        for source_scope, doc, name in self.m.documents(owner, course).values():
            if subject and name != subject:
                continue
            identity = self.m.key(source_scope, doc)
            if identity in seen:
                continue
            seen.add(identity)
            document = {'id': identity, 'name': doc['name'], 'subject': name,
                        'ready': self.m.ready(doc), 'revision': doc.get('contentRevision'),
                        'parseStatus': doc.get('status'), 'ranges': 0,
                        'pendingParse': (source_scope.user_id, source_scope.course_id, doc['id']) in parsing}
            documents.append(document)
            if not document['ready']:
                continue
            batches, parts, used = [], [], 0
            for source in self.m.rag.sources(source_scope, document_ids=[doc['id']]):
                text = source.get('quote', '')
                for start in range(0, len(text), SIZE):
                    end = min(start+SIZE, len(text))
                    part = {'sourceId': source['id'], 'start': start, 'end': end,
                            'hash': digest(text[start:end]), 'page': source.get('page')}
                    if parts and used + end-start > SIZE:
                        batches.append(parts); parts, used = [], 0
                    parts.append(part); used += end-start
            if parts:
                batches.append(parts)
            for parts in batches:
                key = 'cg-' + digest([identity, parts])[:48]
                ranges.append({'id': key, 'documentId': identity, 'page': parts[0].get('page'),
                               'part': parts, 'scope': source_scope.wire(), 'rawId': doc['id'],
                               'revision': doc['contentRevision'], 'saved': artifacts.get(key),
                               'job': jobs.get(key)})
                document['ranges'] += 1
        return scope, documents, ranges

    def read(self, account, owner, course, subject=''):
        scope, documents, ranges = self.inventory(account, owner, course, subject)
        nodes = [{'id': 'course', 'label': subject or '全部可访问课程', 'kind': 'course'}]
        edges, concepts, question_ids, question_keys = [], {}, set(), set()
        for doc in documents:
            nodes.append({'id': doc['id'], 'label': doc['name'], 'kind': 'document', 'subject': doc['subject']})
            edges.append({'source': 'course', 'target': doc['id'], 'relation': 'contains'})
        graph_items = list(ranges)
        for doc in documents:
            if not doc['ready']:continue
            seed = self.p.repo.read(scope, 'artifact', doc['id'])
            if seed:
                graph_items.append({'id': doc['id'], 'documentId': doc['id'], 'page': None,
                                    'part': [], 'saved': seed['value']})
        for item in graph_items:
            if not item['saved']:
                continue
            for node in item['saved']['concepts']:
                normalized = label_key(node['label'])
                # Exact normalized titles only: no unreviewed semantic merging.
                subject_name = next(d['subject'] for d in documents if d['id'] == item['documentId'])
                key = node['id']  # Persisted relation, never a title-based identity
                concept = concepts.setdefault(key, {'id': key, 'label': node['label'], 'kind': 'concept',
                                                     'references': [], 'questionIds': [], 'descriptions': []})
                reference = {'materialId': item['id'], 'conceptId': node['id'], 'documentId': item['documentId'],
                             'page': item['page'], 'ranges': [{'page': p.get('page'), 'start': p['start'], 'end': p['end']} for p in item['part']]}
                concept['references'].append(reference)
                if node.get('description') and node['description'] not in concept['descriptions']:
                    concept['descriptions'].append(node['description'])
                for qid in node['questionIds']:
                    question = self.p.repo.read(scope, 'question', qid)
                    fingerprint = digest([subject_name, question['value'].get('type'), re.sub(r'\s+', '', unicodedata.normalize('NFKC',question['value']['prompt']))]) if question else qid
                    if qid not in question_ids:
                        concept['questionIds'].append(qid)
                        question_ids.add(qid)
                        question_keys.add(fingerprint)
                edge = {'source': item['documentId'], 'target': key, 'relation': 'contains'}
                if edge not in edges:
                    edges.append(edge)
        from .practice_catalog import workspace_catalog
        from .graph_practice import attach_practice
        catalog = workspace_catalog(self.m.app.state.practice_generation, account)
        attach_practice(documents, concepts, edges, catalog['questions'])
        nodes.extend(concepts.values())
        done = sum(bool(r['saved']) for r in ranges)
        blocked = [{'id': r['id'], 'status': r['job']['status'], 'error': r['job'].get('error')}
                   for r in ranges if not r['saved'] and r['job'] and r['job']['status'] in ('failed', 'unknown', 'cancelled')]
        active = sum(bool(r['job'] and r['job']['status'] in ('queued', 'running', 'cancelling')) for r in ranges)
        active += sum(d['pendingParse'] for d in documents)
        identities = {d['id'] for d in documents}
        active += sum(r['idempotency_key'] in identities for r in self.p.db.all(
            "SELECT idempotency_key FROM jobs WHERE user_id=? AND type='material-learning' AND status IN ('queued','running','cancelling')", (scope.user_id,)))
        return {'documents': documents, 'nodes': nodes, 'edges': edges,
                'coverage': {'completedRanges': done, 'totalRanges': len(ranges), 'pendingJobs': active,
                             'remainingCalls': sum(not r['saved'] and not r['job'] for r in ranges),
                             'unreadyDocuments': sum(not d['ready'] for d in documents),
                             'inputComplete': bool(ranges) and done == len(ranges),
                             'independentlyReviewed': False, 'questions': len(question_ids)},
                'blocked': blocked, 'available': bool(self.m.app.state.config.api_key)}

    def submit(self, account, owner, course, subject, limit):
        require(type(limit) is int and 1 <= limit <= 50, 'INVALID_GRAPH_CALL_LIMIT')
        require(bool(self.m.app.state.config.api_key), 'AI_UNAVAILABLE')
        scope, _, ranges = self.inventory(account, owner, course, subject)
        ids = []
        with self.p.db.transaction():
            for item in ranges:
                if item['saved'] or item['job']:
                    continue
                args = {'account': account, 'owner': owner, 'requestCourse': course,
                        'sourceScope': item['scope'], 'documentId': item['rawId'],
                        'revision': item['revision'], 'materialId': item['id'], 'sourcePart': item['part']}
                job = self.p.jobs.submit(scope.user_id, {'type': JOB, 'courseId': scope.course_id,
                    'resource': 'api', 'maxAttempts': 1, 'idempotencyKey': item['id'], 'input': args})
                ids.append(job['id'])
                if len(ids) >= limit:
                    break
        return {'jobIds': ids, 'maximumCalls': len(ids), 'automaticRetry': False}

    async def execute(self, scope, args, **callbacks):
        # Uses original revision/scope, structured quiz validation, source-body
        # protection and shared atomic commit. Unknown jobs are never replayed.
        return await self.m.execute(scope, args, **callbacks)
