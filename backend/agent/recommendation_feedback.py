from ..core import require, clone, fingerprint, now_iso, date_at, valid_date, days_until


class RecommendationFeedback:
    record_id = 'c:recommendation-feedback'

    def __init__(self, repository, clock=now_iso):
        self.repository, self.clock = repository, clock

    async def get(self, course):
        row = await self.repository.get(course, self.record_id)
        require(not row or row['courseId'] == course and row['kind'] == 'recommendation-feedback', 'ARTIFACT_KIND_CONFLICT')
        return row or {'courseId': course, 'id': self.record_id, 'kind': 'recommendation-feedback', 'revision': 0, 'content': {'events': []}}

    async def record(self, value):
        require(isinstance(value.get('itemId'), str) and value['itemId'].strip() and value.get('action') in ('skip', 'dismiss', 'completed', 'restore') and value.get('operationId') and ('until' not in value or valid_date(value['until'])) and isinstance(value.get('reason', ''), str) and len(value.get('reason', '')) <= 2000, 'INVALID_RECOMMENDATION_FEEDBACK')
        digest = fingerprint({k: value.get(k) for k in ('itemId', 'action', 'until', 'expectedRevision')} | {'reason': value.get('reason', '')})
        course, operation = value['courseId'], 'recommendation:'+value['operationId']
        old = await self.repository.get_operation(course, operation)
        if old:
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return old['value']
        until = value.get('until', date_at(self.clock()))
        require(0 <= days_until(until, date_at(self.clock())) <= 365, 'INVALID_RECOMMENDATION_FEEDBACK')
        row = await self.get(course)
        require(row['revision'] == value.get('expectedRevision'), 'ARTIFACT_CONFLICT')
        event = {k: value[k] for k in ('courseId', 'itemId', 'action')} | {'id': value['operationId'], 'until': until, 'reason': value.get('reason', ''), 'createdAt': self.clock()}
        return await self.repository.commit({'courseId': course, 'id': self.record_id, 'operationId': operation, 'requestHash': digest, 'expectedRevision': row['revision'], 'value': {**row, 'revision': row['revision']+1, 'updatedAt': event['createdAt'], 'content': {'events': [*row['content']['events'], event]}}})
