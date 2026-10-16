from ..core import require, clone, fingerprint, now_iso
from .assessment import diagnose

CAUSES = ['knowledge-gap', 'misread', 'calculation', 'method', 'notation', 'input-error', 'uncertain']


class DiagnosisService:
    def __init__(self, repository, clock=now_iso):
        require(hasattr(repository, 'get_operation') and hasattr(repository, 'commit'), 'OPERATION_LOOKUP_REQUIRED')
        self.repository, self.clock = repository, clock

    async def _load(self, course, key):
        row = await self.repository.get(course, key)
        require(row and row['courseId'] == course and row['kind'] == 'attempt', 'ATTEMPT_NOT_FOUND')
        return row

    async def analyze(self, value):
        row = await self._load(value['courseId'], value['attemptId'])
        items = []
        for event in row['content']['events']:
            base = diagnose(event)
            confirmation = next((d for d in row['content']['diagnoses'] if d['eventId'] == event['id'] and d['status'] == 'confirmed'), None)
            items.append(confirmation or {'eventId': event['id'], **base, 'possibleCauses': [c for c in CAUSES if c != 'input-error'] if base['status'] == 'candidate' else [], 'limitation': '没有足够信息推断真实思考过程', 'sourceId': event['sourceId'], 'sourceVersion': event['sourceVersion']})
        return {'courseId': value['courseId'], 'attemptId': value['attemptId'], 'revision': row['revision'], 'items': items}

    async def correct(self, value):
        require(value.get('operationId') and value.get('cause') in CAUSES and isinstance(value.get('reason'), str) and value['reason'].strip() and value.get('confirmedBy'), 'INVALID_DIAGNOSIS_CORRECTION')
        course, operation = value['courseId'], 'diagnosis:'+value['operationId']
        digest = fingerprint({k: value[k] for k in ('attemptId', 'eventId', 'expectedRevision', 'cause', 'reason', 'confirmedBy')})
        old = await self.repository.get_operation(course, operation)
        if old:
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return old['value']
        row = await self._load(course, value['attemptId'])
        require(row['revision'] == value['expectedRevision'], 'ARTIFACT_CONFLICT')
        event = next((e for e in row['content']['events'] if e['id'] == value['eventId']), None)
        require(event and event['grade']['status'] == 'graded', 'GRADED_EVENT_REQUIRED')
        content = clone(row['content'])
        correction = {k: value[k] for k in ('eventId', 'cause', 'reason', 'confirmedBy')} | {'status': 'confirmed', 'createdAt': self.clock(), 'sourceId': event['sourceId'], 'sourceVersion': event['sourceVersion']}
        content['diagnoses'] = [d for d in content['diagnoses'] if d['eventId'] != event['id']]+[correction]
        for e in content['events']:
            if e['id'] == event['id']:
                e['masteryExclusion'] = {k: value[k] for k in ('confirmedBy', 'reason', 'operationId')} if value['cause'] == 'input-error' else None
        return await self.repository.commit({'courseId': course, 'id': row['id'], 'operationId': operation, 'requestHash': digest, 'expectedRevision': row['revision'], 'value': {**row, 'revision': row['revision']+1, 'updatedAt': self.clock(), 'content': content}})
