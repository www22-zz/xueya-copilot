from ..core import require, clone, fingerprint, now_iso


class ArtifactService:
    def __init__(self, repository, clock=now_iso):
        require(hasattr(repository, 'get') and hasattr(repository, 'commit'), 'ARTIFACT_REPOSITORY_REQUIRED')
        self.repository, self.clock = repository, clock

    async def preview(self, value):
        require(all(value.get(k) for k in ('courseId', 'id', 'kind')) and 'content' in value, 'INVALID_ARTIFACT')
        current = await self.repository.get(value['courseId'], value['id'])
        require(not current or current['courseId'] == value['courseId'] and current['kind'] == value['kind'], 'ARTIFACT_KIND_CONFLICT')
        revision = value.get('expectedRevision', 0)
        require((current['revision'] if current else 0) == revision, 'ARTIFACT_CONFLICT')
        draft = {k: clone(value[k]) for k in ('courseId', 'id', 'kind', 'content')}
        draft.update(runId=value.get('runId'), expectedRevision=revision)
        return {**draft, 'digest': fingerprint(draft), 'previous': clone(current['content']) if current else None, 'status': 'preview'}

    async def adopt(self, draft, options):
        require(options.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
        require(options.get('operationId'), 'IDEMPOTENCY_KEY_REQUIRED')
        original = {k: draft[k] for k in ('courseId', 'id', 'kind', 'content', 'runId', 'expectedRevision')}
        require(fingerprint(original) == draft.get('digest'), 'DRAFT_CHANGED')
        return await self.repository.commit({'courseId': draft['courseId'], 'id': draft['id'], 'operationId': options['operationId'],
                    'requestHash': draft['digest'], 'expectedRevision': draft['expectedRevision'],
                    'value': {k: clone(draft[k]) for k in ('courseId', 'id', 'kind', 'content', 'runId')} | {'revision': draft['expectedRevision']+1, 'updatedAt': self.clock()}})
