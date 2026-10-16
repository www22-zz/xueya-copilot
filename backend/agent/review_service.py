from ..core import require, clone, fingerprint, now_iso, date_at, valid_date, days_until, instant, SHANGHAI
from .artifact_service import ArtifactService
from .evidence import evidence_package
from .study import FsrsScheduler


class ReviewService:
    def __init__(self, repository, clock=now_iso, retention=.9):
        require(hasattr(repository, 'get_operation'), 'OPERATION_LOOKUP_REQUIRED')
        self.repository, self.clock, self.retention = repository, clock, retention
        self.artifacts, self.scheduler = ArtifactService(repository, clock), FsrsScheduler(retention)

    async def _load(self, course, key):
        row = await self.repository.get(course, key)
        require(row and row['courseId'] == course and row['kind'] == 'memory-card', 'MEMORY_CARD_NOT_FOUND')
        return row

    async def preview(self, value):
        pack = evidence_package(value)
        prompt, answer, evidence = value.get('prompt'), value.get('answer'), value.get('evidence')
        require(isinstance(prompt, str) and prompt.strip() and len(prompt) <= 4000 and isinstance(answer, str) and answer.strip() and len(answer) <= 8000 and isinstance(evidence, list) and evidence, 'INVALID_MEMORY_CARD')
        refs = []
        for ref in evidence:
            source = next((s for s in pack['sources'] if s['id'] == ref.get('sourceId')), None)
            require(source and isinstance(ref.get('quote'), str) and ref['quote'].strip() and ref['quote'] in source['quote'], 'INVALID_CARD_EVIDENCE')
            refs.append({'sourceId': source['id'], 'documentId': source['documentId'], 'version': source['version'], 'quote': ref['quote']})
        previous = await self.repository.get(value['courseId'], value['id'])
        require(not previous or previous['kind'] == 'memory-card', 'ARTIFACT_KIND_CONFLICT')
        old = previous['content'] if previous else {}
        changed = not previous or fingerprint([prompt, answer, refs]) != fingerprint([old['prompt'], old['answer'], old['evidence']])
        content = {'courseId': value['courseId'], 'cardId': value['id'], 'prompt': prompt, 'answer': answer, 'evidence': refs, 'createdAt': old.get('createdAt', self.clock()),
                   'contentStartedAt': self.clock() if changed else old.get('contentStartedAt', old['createdAt']), 'reviewEvents': old.get('reviewEvents', []), 'schedule': None if changed else old.get('schedule'),
                   'deferredUntil': None if changed else old.get('deferredUntil'), 'deferrals': old.get('deferrals', []), 'contentRevision': old.get('contentRevision', 0)+int(changed)}
        return await self.artifacts.preview({'courseId': value['courseId'], 'id': value['id'], 'kind': 'memory-card', 'content': content, 'expectedRevision': value.get('expectedRevision', 0)})

    async def rate(self, value):
        require(value.get('operationId') and type(value.get('rating')) is int and value['rating'] in (1, 2, 3, 4), 'INVALID_REVIEW_EVENT')
        course, key, revision = value['courseId'], value['id'], value['expectedRevision']
        digest, operation = fingerprint({k: value[k] for k in ('id', 'expectedRevision', 'rating')}), 'review:'+value['operationId']
        old = await self.repository.get_operation(course, operation)
        if old:
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return old['value']
        row = await self._load(course, key)
        require(row['revision'] == revision, 'ARTIFACT_CONFLICT')
        require(len(row['content']['reviewEvents']) < 10000, 'REVIEW_HISTORY_BUDGET')
        content = clone(row['content'])
        event = {'id': value['operationId'], 'courseId': course, 'cardId': key, 'rating': value['rating'], 'createdAt': self.clock(), 'contentRevision': content['contentRevision']}
        content['reviewEvents'].append(event)
        result = self.scheduler.replay([e for e in content['reviewEvents'] if e['contentRevision'] == content['contentRevision']], {'courseId': course, 'cardId': key, 'createdAt': content.get('contentStartedAt', content['createdAt'])})
        due = result['card']['due']
        content.update(schedule={'algorithm': result['algorithm'], 'retention': self.retention, 'personalized': False, 'card': result['card'], 'dueAt': due, 'dueDate': date_at(due)}, deferredUntil=None)
        return await self.repository.commit({'courseId': course, 'id': key, 'operationId': operation, 'requestHash': digest, 'expectedRevision': revision, 'value': {**row, 'revision': revision+1, 'updatedAt': event['createdAt'], 'content': content}})

    async def catalog(self, value):
        ids = value.get('cardIds')
        require(isinstance(ids, list) and len(ids) <= 10000 and all(isinstance(x, str) and x for x in ids), 'INVALID_REVIEW_QUEUE')
        cards = []
        for key in dict.fromkeys(ids):
            row = await self._load(value['courseId'], key)
            content = row['content']
            schedule = content.get('schedule') or {}
            due = schedule.get('dueAt') or content.get('contentStartedAt') or content['createdAt']
            eligible = due
            if content.get('deferredUntil'):
                eligible = max(instant(due), instant(content['deferredUntil']+'T00:00:00+08:00')).isoformat()
            cards.append({'courseId': value['courseId'], 'id': key, 'revision': row['revision'], 'prompt': content['prompt'], 'dueDate': schedule.get('dueDate', date_at(due)), 'dueAt': due, 'eligibleAt': eligible, 'eligibleDate': date_at(eligible),
                          'reviewCount': len(content['reviewEvents']), 'evidence': content['evidence'], 'eventEvidence': [e['id'] for e in content['reviewEvents']]})
        return {'courseId': value['courseId'], 'cards': cards}

    async def defer(self, value):
        until, reason = value.get('until'), value.get('reason', '')
        require(value.get('operationId') and valid_date(until) and isinstance(reason, str) and len(reason) <= 2000, 'INVALID_REVIEW_DEFERRAL')
        course = value['courseId']
        digest = fingerprint({k: value[k] for k in ('id', 'expectedRevision', 'until')} | {'reason': reason})
        operation = 'defer:'+value['operationId']
        old = await self.repository.get_operation(course, operation)
        if old:
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return old['value']
        require(0 <= days_until(until, date_at(self.clock())) <= 365, 'INVALID_REVIEW_DEFERRAL')
        row = await self._load(course, value['id'])
        require(row['revision'] == value['expectedRevision'], 'ARTIFACT_CONFLICT')
        content = {**clone(row['content']), 'deferredUntil': until, 'deferrals': [*row['content'].get('deferrals', []), {'id': value['operationId'], 'until': until, 'reason': reason, 'createdAt': self.clock()}]}
        return await self.repository.commit({'courseId': course, 'id': value['id'], 'operationId': operation, 'requestHash': digest, 'expectedRevision': row['revision'], 'value': {**row, 'revision': row['revision']+1, 'content': content, 'updatedAt': self.clock()}})

    async def queue(self, value):
        base = value.get('baseDate', date_at(self.clock()))
        require(valid_date(base), 'INVALID_REVIEW_QUEUE')
        cutoff = instant(self.clock()) if base == date_at(self.clock()) else instant(base+'T23:59:59.999+08:00')
        cards = [{**c, 'overdueDays': max(0, days_until(base, c['dueDate'])), 'reason': '复习已到期' if c['reviewCount'] else '新记忆卡，尚无复习证据'} for c in (await self.catalog(value))['cards'] if instant(c['eligibleAt']) <= cutoff]
        return {'courseId': value['courseId'], 'baseDate': base, 'cards': sorted(cards, key=lambda c: (c['dueDate'], c['id']))}

    async def history(self, value):
        row = await self._load(value['courseId'], value['id'])
        return {'courseId': value['courseId'], 'id': value['id'], 'revision': row['revision'], **{out: clone(row['content'].get(key)) for out, key in [('events', 'reviewEvents'), ('deferrals', 'deferrals'), ('deferredUntil', 'deferredUntil'), ('schedule', 'schedule')]}}
