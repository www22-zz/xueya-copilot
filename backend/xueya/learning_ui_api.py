"""Page-facing queries and confirmed learning commands on the main platform."""
import base64
import json
from uuid import uuid4
from fastapi.responses import JSONResponse
from backend.core import require, fingerprint, clone, date_at, now_iso, DomainError
from backend.agent.assessment import validate_question
from backend.agent.concepts import validate_graph, build_learning_path
from backend.agent.media_service import MediaService
from backend.providers.mimo import MimoProvider as NativeProvider, MODELS
from .common import AppError
from .execution_budget import current_budget


class TrackedNativeModel:
    """Native image/audio options, with the main host's limiter and durable ledger."""
    def __init__(self, host, course, model):
        self.host, self.scope, self.model = host, host.p.scope(course), model
        config = host.app.state.config
        self.native = NativeProvider({'apiKey': config.api_key, 'baseURL': config.base_url, 'model': model,
                                      'maxRequests': 1000000, 'maxOutputTokens': config.max_output_tokens}, transport=getattr(host.app.state.provider, 'transport', None))

    async def generate(self, value):
        provider = self.host.app.state.provider
        purpose = 'asr' if self.model == 'mimo-v2.5-asr' else 'tts' if self.model == 'mimo-v2.5-tts' else 'image'
        async with provider.invocation(value['messages'], self.scope, capability=purpose, model=self.model) as state:
            index = len(self.native.records)
            try:
                result = await self.native.generate({**value, 'maxOutputTokens': state['outputLimit'],
                    'timeoutMs': min(value.get('timeoutMs', 25000), max(1, int(current_budget.get().remaining()*1000)))})
            except DomainError:
                if len(self.native.records) > index:
                    record = self.native.records[index]
                    if record.get('finishReason'):
                        state.update(complete=True, usage=record.get('usage'), finishReason=record['finishReason'])
                raise
            state.update(complete=True, usage=result.get('usage'), finishReason=result.get('finishReason'))
            provider.check_finish(state['finishReason'])
            require(not result.get('toolCalls'), 'AI_UNEXPECTED_TOOL_CALL')
            current_budget.get().observe(state['usage'], state['reservedCost'], state['outputLimit'])
            current_budget.get().remaining()
            state['usable'] = True
            return result


class Speech:
    def __init__(self, host, course):
        self.asr, self.tts = TrackedNativeModel(host, course, 'mimo-v2.5-asr'), TrackedNativeModel(host, course, 'mimo-v2.5-tts')

    async def transcribe(self, value):
        result = await self.asr.generate({'signal': value.get('signal'), 'asrOptions': {'language': 'auto'},
            'messages': [{'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': value['audio']}}]}]})
        return {'text': result['content'], 'model': result['model']}

    async def synthesize(self, value):
        result = await self.tts.generate({'signal': value.get('signal'), 'audio': {'format': 'wav', 'voice': value.get('voice', 'mimo_default')},
            'messages': [{'role': 'assistant', 'content': value['text']}]})
        data = (result.get('audio') or {}).get('data')
        require(isinstance(data, str) and len(data) <= 20*1024*1024, 'INVALID_SPEECH_RESPONSE')
        try:
            base64.b64decode(data, validate=True)
        except ValueError:
            require(False, 'INVALID_SPEECH_RESPONSE')
        return {'data': data, 'mime': 'audio/wav', 'synthetic': True}


class LearningPages:
    def __init__(self, host):
        self.h, self.p = host, host.p

    async def sources(self, course, selection=None):
        return await self.h.sources({'courseId': course, 'selection': selection})

    async def preview(self, course, value):
        key = str(uuid4())
        await self.h.previews.put(course, key, value)
        return {'draftId': key, 'draft': value}

    async def commit(self, course, key, kind, content, value):
        require(isinstance(value.get('operationId'), str) and value['operationId'] and type(value.get('expectedRevision')) is int, 'IDEMPOTENCY_KEY_REQUIRED')
        digest = fingerprint({'kind': kind, 'id': key, 'request': value})
        return await self.h.repo.commit({'courseId': course, 'id': key, 'operationId': value['operationId'], 'requestHash': digest,
            'expectedRevision': value['expectedRevision'], 'value': {'id': key, 'courseId': course, 'kind': kind,
                'revision': value['expectedRevision']+1, 'content': content, 'updatedAt': now_iso()}})

    async def question(self, course, key):
        row = await self.h.repo.get(course, 'question:'+key)
        require(row and row['kind'] == 'question-draft', 'QUESTION_NOT_FOUND')
        return row

    async def graph(self, course):
        row = await self.h.repo.get(course, 'course-graph')
        return row or {'id': 'course-graph', 'courseId': course, 'revision': 0, 'kind': 'concept-graph',
                       'content': {'courseId': course, 'concepts': [], 'edges': []}}

    def media(self, course):
        factory = getattr(self.h.app.state, 'learning_media_factory', None)
        if factory:
            return factory(self.h, course)
        config = self.h.app.state.config
        speech = Speech(self.h, course) if config.api_key else None
        return MediaService(self.resolve_media, image_model=TrackedNativeModel(self.h, course, config.model) if config.api_key and MODELS.get(config.model, {}).get('image') else None,
                            asr=speech, tts=speech, cache=self.h.checkpoints)

    async def resolve_media(self, value, signal=None):
        row = await self.h.repo.get(value['courseId'], 'media:'+value['id'])
        require(row and row['kind'] == 'media' and str(row['revision']) == str(value['version']), 'MEDIA_NOT_FOUND')
        media = clone(row['content'])
        if media.get('fileHash'):
            media['bytes'] = self.p.files.read(media['fileHash'])
        return media

    async def dispatch(self, path, request, course):
        query, service, scope = request.query_params, self.h.service(course), self.p.scope(course)
        gets = {'workspace', 'artifacts', 'history', 'review-history', 'graph', 'media-result', 'draft'}
        posts = {'questions/generate', 'questions/review', 'questions/edit', 'questions/variant', 'questions/manual',
                 'summary/preview', 'compare', 'graph/extract', 'graph/preview', 'graph/correct', 'graph/path',
                 'note/preview', 'history/preview', 'legacy/import', 'media/recognize', 'media/confirm', 'media/diagnose',
                 'media/transcribe', 'media/video', 'media/video-register', 'media/speak'}
        if path not in gets | posts | {'media/upload'}:
            return None
        if request.method != ('GET' if path in gets else 'POST'):
            return JSONResponse({'ok': False, 'error': 'METHOD_NOT_ALLOWED'}, status_code=405)
        from .app import body, json_body, connected_work
        value = {} if path in gets or path == 'media/upload' else await json_body(request, 1048576)
        if path in gets:
            await body(request, 1024)
        require('courseId' not in value or value['courseId'] == course, 'COURSE_MISMATCH')
        from .common import identifier
        if 'id' in value:
            identifier(value['id'])

        async def execute():
            if path == 'workspace':
                try:
                    selection = {'documentIds': json.loads(query['documentIds'])} if query.get('documentIds') else None
                    sources = await self.h.sources({'courseId': course, 'selection': selection}, catalog=True)
                except DomainError as error:
                    if error.code != 'NO_SOURCES':
                        raise
                    sources = []
                rows = self.h.repo.all(course)
                if query.get('kinds'):
                    kinds = query['kinds'].split(',')
                    require(len(kinds) <= 10, 'INVALID_FILTER')
                    rows = [r for r in rows if r.get('kind') in kinds]
                rows.sort(key=lambda r: r['id'])
                config = self.h.app.state.config
                return {'artifacts': rows[:20], 'hasMore': len(rows) > 20, 'nextArtifact': rows[19]['id'] if len(rows) > 20 else None, 'sources': sources,
                    'runs': sorted(self.h.runs.all(course), key=lambda r: r['updatedAt'], reverse=True)[:30],
                    'graph': await self.graph(course), 'feedback': await service.feedback.get(course),
                    'documents': [d for d in self.p.repo.all(scope, 'document') if not d.get('superseded') and not d.get('archived')],
                    'ragCapabilities': {'ocr': bool(getattr(self.h.app.state.rag, 'ocr', None)), 'embedding': bool(getattr(self.h.app.state.rag, 'embedding', None))},
                    'capabilities': {'model': bool(config.api_key), 'image': bool(config.api_key and MODELS.get(config.model, {}).get('image')),
                                     'speech': bool(config.api_key), 'mediaTestAdapter': bool(getattr(self.h.app.state, 'learning_media_factory', None))}}
            if path == 'artifacts':
                key = query.get('id')
                if key:
                    row = await self.h.repo.get(course, key)
                    require(row is not None, 'ARTIFACT_NOT_FOUND')
                    return row
                rows = sorted(self.h.repo.all(course), key=lambda r: r['id'])
                after, kind = query.get('after', ''), query.get('kind')
                rows = [r for r in rows if r['id'] > after and (not kind or r.get('kind') == kind)]
                if query.get('kinds'):
                    kinds = query['kinds'].split(',')
                    require(len(kinds) <= 10, 'INVALID_FILTER')
                    rows = [r for r in rows if r.get('kind') in kinds]
                return {'items': rows[:20], 'next': rows[19]['id'] if len(rows) > 20 else None}
            if path == 'draft':
                draft = await self.h.previews.get(course, query.get('id', ''))
                require(draft and draft['courseId'] == course, 'DRAFT_NOT_FOUND')
                return {'draftId': query['id'], 'draft': draft}
            if path == 'history':
                key = query.get('id', '')
                await self.h.repo.get(course, key)
                rows = self.p.db.all('SELECT version,data,at FROM revisions WHERE user_id=? AND course_id=? AND kind=? AND id=? ORDER BY version DESC LIMIT 30',
                    (scope.user_id, course, 'artifact', self.h.repo.key(key)))
                return {'items': [{'version': r['version'], 'at': r['at'], 'value': json.loads(r['data'])} for r in rows]}
            if path == 'review-history':
                return await service.reviews.history({'courseId': course, 'id': query.get('id')})
            if path == 'graph':
                return await self.graph(course)
            if path == 'media-result':
                row = await self.h.repo.get(course, 'recognition:'+query.get('id', ''))
                require(row, 'MEDIA_RESULT_NOT_FOUND')
                return row
            if path.startswith('questions/'):
                sources = await self.sources(course, value.get('selection'))
                if path in ('questions/generate', 'questions/variant'):
                    args = {'courseId': course, 'sources': sources, **{k: value[k] for k in ('count', 'types', 'conceptIds') if k in value}}
                    args['existing'] = [r['content'] for r in self.h.repo.all(course) if r.get('kind') == 'question-draft']
                    if path == 'questions/variant':
                        args['parent'] = (await self.question(course, value['id']))['content']
                    generated = await service.questions.generate(args)
                    for q in generated['questions']:
                        existing = await self.h.repo.get(course, 'question:'+q['id'])
                        if not existing:
                            await self.commit(course, 'question:'+q['id'], 'question-draft', q, {'expectedRevision': 0, 'operationId': 'generated:'+q['id']})
                    return generated
                if path == 'questions/manual':
                    q = value.get('question', {})
                    source = next((s for s in sources if s['id'] == q.get('sourceId')), None)
                    require(source, 'INVALID_QUESTION_EVIDENCE')
                    q = validate_question({**q, 'id': value.get('id') or 'q-'+str(uuid4()), 'courseId': course,
                        'sourceVersion': source['version'], 'version': fingerprint(q)[:24], 'status': 'candidate'}, sources)
                    return await self.commit(course, 'question:'+q['id'], 'question-draft', q, value)
                row = await self.question(course, value['id'])
                previous = await self.h.repo.get_operation(course, value.get('operationId'))
                if previous:
                    require(previous['requestHash'] == fingerprint({'kind': 'question-draft', 'id': row['id'], 'request': value}), 'IDEMPOTENCY_CONFLICT')
                    return previous['value']
                if path == 'questions/edit':
                    q = service.questions.edit_question(row['content'], value['patch'], sources)
                else:
                    q = service.questions.review_question(row['content'], {'expectedVersion': value['expectedVersion'],
                        'approved': value['approved'], 'reviewer': self.p.user_id, 'reason': value.get('reason', '')}, sources)
                with self.p.db.transaction():
                    stored = await self.commit(course, row['id'], 'question-draft', q, value)
                    current = self.p.repo.read(scope, 'question', q['id'], include_deleted=True)
                    self.p.repo.put(scope, 'question', q['id'], {**q, 'learningManaged': True}, current['version'] if current else 0, deleted=q['status'] != 'approved')
                return stored
            if path == 'note/preview':
                require(isinstance(value.get('text'), str) and 0 < len(value['text'].strip()) <= 120000, 'INVALID_NOTE')
                draft = await service.artifacts.preview({'courseId': course, 'id': value['id'], 'kind': 'note',
                    'expectedRevision': value.get('expectedRevision', 0), 'content': {'title': str(value.get('title', '课程笔记'))[:160], 'text': value['text'], 'editedBy': 'user'}})
                return await self.preview(course, draft)
            if path == 'history/preview':
                current = await self.h.repo.get(course, value['id'])
                require(current and current['kind'] == 'note', 'NOTE_NOT_FOUND')
                require(type(value.get('version')) is int and current['revision'] == value['expectedRevision'], 'ARTIFACT_CONFLICT')
                row = self.p.db.one('SELECT data FROM revisions WHERE user_id=? AND course_id=? AND kind=? AND id=? AND version=?',
                    (scope.user_id, course, 'artifact', self.h.repo.key(value['id']), value['version']))
                require(row, 'VERSION_NOT_FOUND')
                content = json.loads(row['data'])['content']
                draft = await service.artifacts.preview({'id': current['id'], 'courseId': course, 'kind': 'note',
                    'expectedRevision': current['revision'], 'content': content})
                return await self.preview(course, draft)
            if path in ('summary/preview', 'compare'):
                args = {'courseId': course, 'sources': await self.sources(course, value.get('selection'))}
                content = await (service.content.compare(args) if path == 'compare' else service.content.summarize(args))
                draft = await service.artifacts.preview({**args, 'id': value['id'], 'kind': 'comparison' if path == 'compare' else 'chapter-summary', 'content': content, 'expectedRevision': value.get('expectedRevision', 0)})
                return await self.preview(course, draft)
            if path.startswith('graph/'):
                current = await self.graph(course)
                empty_graph = path == 'graph/preview' and value.get('graph', {}).get('concepts') == [] and value.get('graph', {}).get('edges') == []
                sources = [] if empty_graph else await self.sources(course, value.get('selection'))
                if path == 'graph/path':
                    scoped = self.h.scope_study_context({'graph': current['content']}, sources)['graph']
                    validate_graph(scoped, sources)
                    return build_learning_path({'courseId': course, 'graph': scoped, 'estimates': [], **({'targetIds': value['targetIds']} if value.get('targetIds') else {})})
                if path == 'graph/extract':
                    graph = (await service.concepts.extract({'courseId': course, 'sources': sources, 'existing': current['content']}))['graph']
                elif path == 'graph/correct':
                    graph = service.concepts.correct(current['content'], {**value, 'reviewer': self.p.user_id}, sources)
                else:
                    graph = validate_graph(value.get('graph', {}), sources)
                    require(graph['courseId'] == course, 'COURSE_MISMATCH')
                draft = await service.artifacts.preview({'courseId': course, 'id': 'course-graph', 'kind': 'concept-graph', 'content': graph, 'expectedRevision': value['expectedRevision']})
                return await self.preview(course, draft)
            if path == 'legacy/import':
                return await self.import_legacy(course, service, value)
            if path == 'media/upload':
                data = await body(request, 52_428_800)
                mime = request.headers.get('content-type', '').split(';')[0]
                kind = 'image' if mime in ('image/png', 'image/jpeg', 'image/webp') else 'audio' if mime in ('audio/wav', 'audio/mpeg', 'audio/mp3') else 'video' if mime in ('video/mp4', 'video/webm') else None
                require(kind and data and len(data) <= (8*1024*1024 if kind == 'image' else 7*1024*1024 if kind == 'audio' else 50*1024*1024), 'INVALID_MEDIA')
                key, file = str(uuid4()), self.p.files.put(data)
                media = {'courseId': course, 'id': key, 'version': '1', 'kind': kind, 'mime': mime, 'fileHash': file['hash'], 'name': query.get('name', '学习文件')[:200]}
                if kind == 'audio' or kind == 'video' and query.get('durationMs'):
                    duration = int(query.get('durationMs', 0))
                    require(0 < duration <= 1800000, 'INVALID_AUDIO_TIMELINE')
                    media.update(startMs=0, endMs=duration, durationMs=duration)
                await self.commit(course, 'media:'+key, 'media', media, {'expectedRevision': 0, 'operationId': 'upload:'+key})
                return media
            media_service = self.media(course)
            if path == 'media/video-register':
                row = await self.h.repo.get(course, 'media:'+value['id'])
                require(row and row['content']['kind'] == 'video' and type(value.get('durationMs')) in (int, float) and 0 < value['durationMs'] <= 1800000, 'INVALID_VIDEO_SAMPLING')
                frames = value.get('frames')
                require(isinstance(frames, list) and 0 < len(frames) <= 6, 'INVALID_VIDEO_SAMPLING')
                times = []
                for frame in frames:
                    resolved = await self.resolve_media({'courseId': course, 'id': frame['id'], 'version': frame['version']})
                    require(resolved['kind'] == 'image', 'INVALID_VIDEO_FRAME')
                    require(type(frame.get('timeMs')) in (int, float) and 0 <= frame['timeMs'] <= value['durationMs'], 'INVALID_FRAME_TIME')
                    times.append(frame['timeMs'])
                require(times == sorted(set(times)), 'INVALID_FRAME_TIME')
                content = {**row['content'], 'version': str(row['revision']+1), 'frames': frames, 'durationMs': value['durationMs'], 'timelineOrigin': 'browser-sampled'}
                return await self.commit(course, row['id'], 'media', content, value)
            if path == 'media/recognize':
                result = await media_service.image_question({**value, 'courseId': course})
            elif path == 'media/confirm':
                row = await self.h.repo.get(course, 'recognition:'+value['id'])
                require(row and row['revision'] == value['expectedRevision'], 'RECOGNITION_CONFLICT')
                result = media_service.confirm_recognition(row['content'], {'confirmed': value.get('confirmed'), 'correctedProblem': value.get('correctedProblem')})
                return await self.commit(course, row['id'], 'recognition', result, value)
            elif path == 'media/diagnose':
                row = await self.h.repo.get(course, 'recognition:'+value['id'])
                require(row and row['revision'] == value['expectedRevision'], 'RECOGNITION_CONFLICT')
                return await media_service.photo_diagnosis({'recognition': row['content'], 'steps': value['steps'], 'sources': await self.sources(course, value.get('selection')), 'hintsOnly': value.get('hintsOnly', True)})
            elif path == 'media/transcribe':
                result = await media_service.transcribe({'courseId': course, 'segments': value['segments']})
                key = 'transcription-'+fingerprint(value['segments'])[:32]
                old = await self.h.repo.get(course, key)
                await self.commit(course, key, 'transcription', result, {'expectedRevision': old['revision'] if old else 0, 'operationId': 'transcription:'+str(uuid4())})
                return result
            elif path == 'media/video':
                result = await media_service.video_question({**value, 'courseId': course})
                key = 'video-analysis-'+fingerprint(value)[:32]
                old = await self.h.repo.get(course, key)
                await self.commit(course, key, 'video-analysis', result, {'expectedRevision': old['revision'] if old else 0, 'operationId': 'video-analysis:'+str(uuid4())})
                return result
            elif path == 'media/speak':
                artifact = await self.h.repo.get(course, value['id'])
                require(artifact and artifact['revision'] == value['revision'], 'ARTIFACT_CONFLICT')
                c = artifact['content']
                if artifact['kind'] == 'learning-package':
                    c = c['summary']
                text = c.get('text') or c.get('answer') or '\n'.join(x['text'] for x in c.get('claims', []) if x.get('support') == 'supported')
                require(text and value.get('confirmed') is True, 'VERIFIED_TEXT_REQUIRED')
                return await media_service.speak({'courseId': course, 'artifactId': artifact['id'], 'revision': artifact['revision'], 'verified': True, 'text': text, 'voice': value.get('voice', 'mimo_default')})
            else:
                return None
            key = 'recognition:'+value['id']
            old = await self.h.repo.get(course, key)
            return await self.commit(course, key, 'recognition', result, {'expectedRevision': old['revision'] if old else 0, 'operationId': 'recognize:'+str(uuid4())})

        try:
            result = await connected_work(request, execute()) if path != 'media/upload' else await execute()
            return JSONResponse({'ok': True, 'result': result})
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, DomainError):
                raise
            raise DomainError('INVALID_LEARNING_REQUEST') from error

    async def import_legacy(self, course, service, value):
        """Import only server-held source/answer records after explicit confirmation."""
        require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
        sources = await self.sources(course)
        by_id = {s['id']: s for s in sources}
        scope, imported, excluded = self.p.scope(course), 0, []
        for q in self.p.repo.all(scope, 'question'):
            if q.get('courseId') == course and q.get('sourceVersion'):
                continue
            source = by_id.get(q.get('sourceId'))
            if not source:
                excluded.append({'id': q['id'], 'reason': '没有可核对的服务端原文'})
                continue
            try:
                checked = validate_question({**q, 'courseId': course, 'type': q.get('type', 'single'), 'version': str(q['version']),
                    'sourceVersion': source['version'], 'evidenceQuote': q.get('evidenceQuote') or source['quote'], 'status': 'candidate'}, sources)
            except DomainError:
                excluded.append({'id': q['id'], 'reason': '题目结构无法完整转换，原记录保留'})
                continue
            if not await self.h.repo.get(course, 'question:'+q['id']):
                await self.commit(course, 'question:'+q['id'], 'question-draft', checked, {'expectedRevision': 0, 'operationId': 'legacy-question:'+q['id']})
                imported += 1
        legacy_attempts = [a for a in self.p.repo.all(scope, 'attempt') if not a.get('sourceVersion')]
        return {'importedCandidates': imported, 'excluded': excluded, 'legacyAttemptsRetained': len(legacy_attempts),
                'message': '旧作答记录完整保留；缺少当时原文/题目版本的记录不用于新的掌握度计算。候选题需要重新审核。'}
