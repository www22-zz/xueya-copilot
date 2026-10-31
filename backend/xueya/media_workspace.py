"""G5: durable segment jobs over the existing platform, speech ports and evidence."""
import asyncio
import base64
import io
import json
import math
import zipfile
from uuid import uuid4

from fastapi.responses import JSONResponse, Response
from backend.agent.media_audio import MAX_ORIGINAL, VOICES, assemble_wav, make_script, split_wav, srt_timestamp, validate_script, wav_info
from backend.core import DomainError, clone, fingerprint, now_iso
from .common import AppError, identifier, require
from .rag_api import borrowed_api_permit


class MediaWorkspace:
    def __init__(self, host):
        self.h, self.p = host, host.p
        self.p.jobs.register('media-segment-prepare', self.prepare)
        self.p.jobs.register('media-segment-api', self.execute)
        for course in self.p.repo.courses(self.p.scope_user_id):
            if course['archived']:
                continue
            for row in self.h.repo.all(course['id']):
                if row['kind'] == 'media-run' and row['content']['status'] in ('running', 'queued'):
                    self.save(course['id'], row['id'], 'media-run', {**row['content'], 'status': 'unknown', 'error': 'INTERRUPTED_REQUIRES_REVIEW'})

    def identity(self):
        c = self.h.app.state.config
        return fingerprint([c.base_url, c.model, fingerprint(c.api_key), 'asr-tts-g5-v1'])

    def save(self, course, key, kind, content):
        old = self.p.repo.read(self.p.scope(course), 'artifact', self.h.repo.key(key))
        require(not old or old['value']['kind'] == kind, 'ARTIFACT_KIND_CONFLICT')
        row = {'id': key, 'courseId': course, 'kind': kind, 'revision': (old['value']['revision'] if old else 0)+1,
               'content': clone(content), 'updatedAt': now_iso()}
        self.p.repo.put(self.p.scope(course), 'artifact', self.h.repo.key(key), row, old['version'] if old else 0)
        return row

    async def get(self, course, key, kind=None):
        identifier(key)
        row = await self.h.repo.get(course, key)
        require(row and (kind is None or row['kind'] == kind), 'MEDIA_ITEM_NOT_FOUND')
        return row

    async def media(self, course, key, version):
        row = await self.get(course, 'media:'+str(key), 'media')
        require(str(row['revision']) == str(version), 'MEDIA_VERSION_CONFLICT')
        if row['content'].get('originalMediaId'):
            original = await self.get(course, 'media:'+row['content']['originalMediaId'], 'media')
            require(original['revision'] == row['content']['originalMediaVersion'], 'MEDIA_VERSION_CONFLICT')
        return row

    async def original(self, course, media):
        c = media['content']
        return await self.media(course, c['originalMediaId'], c['originalMediaVersion']) if c.get('originalMediaId') else media

    async def checked_script(self, course, key, revision):
        row = await self.get(course, key, 'review-script')
        require(row['revision'] == revision, 'ARTIFACT_CONFLICT')
        sources = await self.h.sources({'courseId': course}, generation=False)
        validate_script(row['content'], sources)
        for parent in row['content'].get('parents', []):
            current = await self.get(course, parent['id'])
            require(current['revision'] == parent['revision'], 'STALE_SCRIPT_PARENT')
        return row

    def enqueue(self, course, key, run, resource='api', prepare=False):
        job = self.p.jobs.submit(self.p.scope_user_id, {'type': 'media-segment-prepare' if prepare else 'media-segment-api',
            'courseId': course, 'resource': resource, 'maxAttempts': 1,
            'idempotencyKey': key+':'+str(run.get('step', 0)), 'input': {'runId': key, 'step': run.get('step', 0)}})
        run['jobId'] = job['id']; run['jobIds'] = run.get('jobIds', [])+[job['id']]
        self.save(course, key, 'media-run', run)
        return job

    async def start(self, course, value, mode):
        operation = identifier(value.get('operationId'))
        key = 'g5-run-'+fingerprint([course, operation])[:36]
        request_hash = fingerprint([mode, value])
        existing = await self.h.repo.get(course, key)
        if existing:
            require(existing['kind'] == 'media-run' and existing['content'].get('requestHash') == request_hash, 'IDEMPOTENCY_CONFLICT')
            return existing
        require(value.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
        run = {'mode': mode, 'status': 'queued', 'step': 0, 'requestHash': request_hash, 'configurationIdentity': self.identity(),
               'items': [], 'createdAt': now_iso(), 'masteryUpdated': False}
        old = None
        if value.get('resumeId'):
            previous = await self.get(course, value['resumeId'], 'media-run')
            old = previous['content']
            require(old['mode'] == mode and old['status'] in ('unknown', 'cancelled', 'failed')
                    and value.get('reviewedUnknown') is True, 'UNKNOWN_OUTCOME_REQUIRES_REVIEW')
            require(old['configurationIdentity'] == self.identity(), 'CONFIGURATION_CHANGED_START_NEW')
            run.update({k: clone(old[k]) for k in ('items', 'mediaId', 'mediaVersion', 'scriptId', 'scriptRevision', 'voices') if k in old})
            run['resumeOf'] = previous['id']
        if mode in ('prepare', 'transcribe', 'video'):
            if old:
                media = await self.media(course, run['mediaId'], run['mediaVersion'])
            else:
                media = await self.media(course, value.get('mediaId'), value.get('mediaVersion'))
                run.update(mediaId=media['content']['id'], mediaVersion=media['revision'])
            require(media['content']['kind'] == ('video' if mode == 'video' else 'audio'), 'INVALID_MEDIA_KIND')
            if mode == 'prepare':
                require(media['content']['mime'] == 'audio/wav', 'PCM_WAV_REQUIRED')
                require(type(value.get('seconds', 120)) is int and 30 <= value.get('seconds', 120) <= 180, 'INVALID_SEGMENT_SECONDS')
                run['seconds'] = value.get('seconds', 120)
            elif not old:
                if mode == 'transcribe':
                    prepared = await self.get(course, value.get('preparedId'), 'media-run')
                    c = prepared['content']
                    require(c['mode'] == 'prepare' and c['status'] == 'completed' and c['mediaId'] == run['mediaId'] and c['mediaVersion'] == run['mediaVersion'], 'AUDIO_NOT_PREPARED')
                    run['items'] = clone(c['items'])
                else:
                    require(media['content'].get('frames'), 'VIDEO_FRAMES_REQUIRED')
                    run['items'] = clone(media['content']['frames'])
                    run['coverage'] = 'sampled-frames-only'
                    run['question'] = str(value.get('question') or '描述可见内容，区分观察、不确定与推断。')[:2000]
            if mode == 'video' and old:
                run['question'] = old['question']; run['coverage'] = old['coverage']
        if mode == 'synthesize':
            script = await self.checked_script(course, run.get('scriptId', value.get('scriptId')), run.get('scriptRevision', value.get('scriptRevision')))
            voices = run.get('voices') or value.get('voices') or {'A': '冰糖', 'B': '苏打'}
            require(isinstance(voices, dict) and set(voices) == {'A', 'B'} and all(v in VOICES for v in voices.values()), 'INVALID_VOICE')
            run.update(scriptId=script['id'], scriptRevision=script['revision'], voices=voices)
            if not old:
                run['items'] = clone(script['content']['segments'])
        if mode != 'prepare':
            require(value.get('allowApi') is True, 'API_CONFIRMATION_REQUIRED')
            service = self.h.pages.media(course)
            require(getattr(service, 'tts' if mode == 'synthesize' else 'asr' if mode == 'transcribe' else 'image_model', None), 'MEDIA_PROVIDER_NOT_CONFIGURED')
            # Reuse only same-configuration/same-text/voice audio; never a new script revision key.
            if mode == 'synthesize':
                for part in run['items']:
                    if part['kind'] == 'pause':
                        part['done'] = True; continue
                    part['cacheKey'] = fingerprint([course, self.identity(), part['text'], voices[part['speaker']]])
                    cached = await self.h.checkpoints.get(course, 'g5-tts:'+part['cacheKey'])
                    if cached:
                        self.p.files.read(cached['audioHash'])
                        part.update(cached, done=True, reused=True)
            pending = sum(not part.get('done') and part.get('kind') != 'pause' for part in run['items'])
            require(type(value.get('maxCalls')) is int and pending <= value['maxCalls'] <= 120, 'API_CALL_BUDGET_REQUIRED')
            run['maxCalls'] = value['maxCalls']; run['calls'] = 0
        with self.p.db.transaction():
            self.enqueue(course, key, run, 'cpu' if mode == 'prepare' or all(p.get('done') for p in run['items']) else 'api', mode == 'prepare')
        return await self.get(course, key)

    async def prepare(self, scope, args, *, progress, checkpoint, commit):
        try:
            return await self._prepare(scope, args, progress=progress, checkpoint=checkpoint, commit=commit)
        except (Exception, asyncio.CancelledError) as error:
            row = await self.get(scope.course_id, args['runId'], 'media-run')
            self.save(scope.course_id, row['id'], 'media-run', {**row['content'],
                'status': 'cancelled' if isinstance(error, asyncio.CancelledError) else 'failed', 'error': getattr(error, 'code', 'MEDIA_PREPARE_FAILED')})
            raise

    async def _prepare(self, scope, args, *, progress, checkpoint, commit):
        row = await self.get(scope.course_id, args['runId'], 'media-run'); run = clone(row['content'])
        require(run['mode'] == 'prepare' and run['status'] == 'queued', 'NOT_SENT')
        media = await self.media(scope.course_id, run['mediaId'], run['mediaVersion'])
        raw = await asyncio.to_thread(self.p.files.read, media['content']['fileHash'])
        info, parts = await asyncio.to_thread(split_wav, raw, run['seconds'])
        for i, part in enumerate(parts):
            original = await asyncio.to_thread(self.p.files.put, part.pop('bytes'))
            part.update(audioHash=original['hash'], mime='audio/wav', id='clip-'+str(i))
            progress({'percent': round((i+1)*100/len(parts)), 'completed': i+1, 'total': len(parts), 'label': '按真实采样边界分段'})
        await self.media(scope.course_id, run['mediaId'], run['mediaVersion'])
        run.update(status='completed', items=parts, audioInfo=info)
        commit(lambda: self.save(scope.course_id, row['id'], 'media-run', run))
        checkpoint({'runId': row['id'], 'completed': len(parts)})
        return {'runId': row['id'], 'completed': len(parts)}

    async def execute(self, scope, args, *, progress, checkpoint, commit):
        course = scope.course_id
        row = await self.get(course, args['runId'], 'media-run'); run = clone(row['content'])
        job = self.p.jobs.get(run['jobId'], scope.user_id)
        require(job and job['attempts'] == 1 and run['step'] == args['step'] and run['status'] in ('queued', 'running'), 'NOT_SENT')
        try:
            require(run['configurationIdentity'] == self.identity(), 'NOT_SENT')
            if run['mode'] == 'synthesize':
                await self.checked_script(course, run['scriptId'], run['scriptRevision'])
            else:
                await self.media(course, run['mediaId'], run['mediaVersion'])
            run['status'] = 'running'; self.save(course, row['id'], 'media-run', run)
            part = next((p for p in run['items'] if not p.get('done')), None)
            if part:
                require(job['resource'] == 'api' and run['calls'] < run['maxCalls'], 'NOT_SENT')
                service = self.h.pages.media(course)
                # One provider request per queue job stays below the shared host timeout.
                with borrowed_api_permit(self.p):
                    if run['mode'] == 'transcribe':
                        audio = 'data:audio/wav;base64,'+base64.b64encode(self.p.files.read(part['audioHash'])).decode()
                        result = await service.asr.transcribe({'audio': audio})
                        require(isinstance(result.get('text'), str) and len(result['text']) <= 20000, 'INVALID_TRANSCRIPTION')
                        part.update(text=result['text'], originalText=result['text'], reviewed=False, timestampPrecision='segment')
                    elif run['mode'] == 'video':
                        result = await service.image_question({'courseId': course, 'id': part['id'], 'version': part['version'], 'question': run['question']})
                        part.update(analysis=result, text='\n'.join(result['observations']), originalText='\n'.join(result['observations']), reviewed=False)
                    else:
                        result = await service.tts.synthesize({'text': part['text'], 'voice': run['voices'][part['speaker']]})
                        require(isinstance(result.get('data'), str) and len(result['data']) <= 14_000_000, 'INVALID_SPEECH_RESPONSE')
                        try:
                            raw = base64.b64decode(result['data'], validate=True)
                        except ValueError as error:
                            raise AppError('INVALID_SPEECH_RESPONSE') from error
                        info = wav_info(raw); file = self.p.files.put(raw)
                        part.update(audioHash=file['hash'], durationMs=info['durationMs'], synthetic=True)
                        await self.h.checkpoints.put(course, 'g5-tts:'+part['cacheKey'], {'audioHash': file['hash'], 'durationMs': info['durationMs'], 'synthetic': True})
                run['calls'] += 1; part['done'] = True
            # Do not publish late results if the original or script changed during inference.
            if run['mode'] == 'synthesize':
                await self.checked_script(course, run['scriptId'], run['scriptRevision'])
            else:
                await self.media(course, run['mediaId'], run['mediaVersion'])
            done = sum(bool(p.get('done')) for p in run['items'])
            progress({'percent': round(100*done/len(run['items'])), 'completed': done, 'total': len(run['items']), 'label': '已逐段保存，未完成段不会自动重试'})
            checkpoint({'runId': row['id'], 'completed': done})
            def finish():
                run.update(status='completed' if done == len(run['items']) else 'queued', step=run['step']+1)
                if run['status'] == 'completed':
                    self.save(course, row['id'], 'media-run', run)
                else:
                    self.enqueue(course, row['id'], run)
            commit(finish)
            return {'runId': row['id'], 'completed': done, 'status': run['status']}
        except (Exception, asyncio.CancelledError) as error:
            code = getattr(error, 'code', 'MEDIA_PROVIDER_OUTCOME_UNKNOWN')
            run.update(status='failed' if code == 'NOT_SENT' else 'unknown', error=code)
            self.save(course, row['id'], 'media-run', run)
            raise

    async def build_script(self, course, value):
        sources = await self.h.sources({'courseId': course, 'selection': value.get('selection')}, generation=False)
        parents, ids, references = [], set(), []
        requested = value.get('parentIds', [])
        require(isinstance(requested, list) and len(requested) <= 6 and all(isinstance(k, str) for k in requested), 'INVALID_SCRIPT_INPUT')
        cards = value.get('cardIds', [])
        require(isinstance(cards, list) and len(cards) <= 20 and all(isinstance(k, str) for k in cards), 'INVALID_REVIEW_CARDS')
        if value.get('focus') == 'due':
            from backend.core import today
            ids = [r['id'] for r in self.h.repo.all(course) if r['kind'] == 'memory-card']
            catalog = await self.h.service(course).reviews.catalog({'courseId': course, 'cardIds': ids})
            cards = [r['id'] for r in catalog['cards'] if r['eligibleDate'] <= today()][:6]
            require(cards, 'NO_DUE_REVIEW_CARDS')
        for key in list(dict.fromkeys(requested+cards)):
            parent = await self.get(course, key)
            require(parent['kind'] in ('note', 'memory-card', 'template-result', 'chapter-summary', 'learning-package'), 'INVALID_SCRIPT_PARENT')
            if key in cards:
                require(parent['kind'] == 'memory-card', 'INVALID_REVIEW_CARDS')
            parents.append({'id': parent['id'], 'revision': parent['revision']})
            def refs(obj):
                if isinstance(obj, dict):
                    if obj.get('sourceId'):
                        ids.add(obj['sourceId'])
                        if obj.get('quote'):
                            references.append(obj)
                    for child in obj.values(): refs(child)
                elif isinstance(obj, list):
                    for child in obj: refs(child)
            refs(parent['content'])
        if parents:
            require(ids, 'NO_VERIFIED_NOTE_EVIDENCE')
            sources = [s for s in sources if s['id'] in ids]
            require({s['id'] for s in sources} == ids, 'STALE_SCRIPT_PARENT')
            by_id = {s['id']: s for s in sources}
            for ref in references:
                require(str(ref.get('version', ref.get('sourceVersion'))) == str(by_id[ref['sourceId']]['version'])
                        and ref['quote'] in by_id[ref['sourceId']]['quote'], 'STALE_SCRIPT_PARENT')
        require(sources, 'NO_SOURCES')
        content = make_script(sources[:6], value.get('style', 'solo'), str(value.get('title') or '课程复习'), cards)
        content.update(parents=parents, omittedSourceCount=max(0, len(sources)-6))
        return {'content': content, 'sources': sources[:6], 'paidCalls': 0}

    async def import_transcript(self, course, value):
        row = await self.get(course, value.get('id'), 'media-run'); c = row['content']
        require(c['mode'] in ('transcribe', 'video') and c['status'] == 'completed' and value.get('confirmed') is True, 'TRANSCRIPT_REVIEW_REQUIRED')
        require(row['revision'] == value.get('revision') and all(p.get('reviewed') for p in c['items']), 'ARTIFACT_CONFLICT')
        processed = await self.media(course, c['mediaId'], c['mediaVersion'])
        media = await self.original(course, processed)
        operation = identifier(value.get('operationId'))
        signature = fingerprint([row['id'], row['revision']])
        label = '人工核对片段转写' if c['mode'] == 'transcribe' else '人工核对采样画面说明，非完整视频转写'
        text = '# '+media['content']['name']+'（'+label+'）\n\n'+'\n\n'.join(f"## {p.get('startMs', p.get('timeMs', 0))/1000:.3f} 秒\n{p['text']}" for p in c['items'])
        library = self.h.app.state.library
        with self.p.db.transaction():
            job = library.text_import(self.p.scope(course), {'text': text, 'title': media['content']['name']+' 转写', 'chapter': str(value.get('chapter', ''))[:160],
                'idempotencyKey': 'g5-import-'+operation}, {'type': 'media-transcript' if c['mode'] == 'transcribe' else 'media-sampled-frame-notes', 'mediaId': media['content']['id'], 'mediaVersion': media['revision'],
                'processingMediaId': c['mediaId'], 'processingMediaVersion': c['mediaVersion'],
                'runId': row['id'], 'runRevision': row['revision'], 'contentHash': signature, 'timestampPrecision': 'segment' if c['mode'] == 'transcribe' else 'sampled-frame'})
            payload = json.loads(self.p.db.one('SELECT input FROM jobs WHERE id=?', (job['id'],))['input'])
            doc = library.rag.document(self.p.scope(course), payload['documentId'])
        return {'job': job, 'documentId': doc['id']}

    async def dispatch(self, path, request, course):
        if not path.startswith('media-workspace/'):
            return None
        from .app import body, json_body
        operation, q = path[len('media-workspace/'):], request.query_params
        self.p.repo.require_course(self.p.scope(course))
        gets = {'workspace', 'result', 'audio', 'export'}
        if request.method != ('GET' if operation in gets else 'POST'):
            return JSONResponse({'ok': False, 'error': 'METHOD_NOT_ALLOWED'}, status_code=405)
        try:
            if operation in ('upload', 'upload-original'):
                mime = request.headers.get('content-type', '').split(';')[0]
                require(mime == 'audio/wav' if operation == 'upload' else mime in ('audio/mpeg','audio/mp3','audio/mp4','audio/aac','audio/flac','audio/x-flac','audio/ogg','audio/webm','video/webm','audio/wav','audio/x-wav','application/octet-stream'), 'UNSUPPORTED_AUDIO_CONTAINER')
                raw = await body(request, MAX_ORIGINAL)
                require(raw, 'INVALID_MEDIA')
                info = await asyncio.to_thread(wav_info, raw) if operation == 'upload' else None
                file = await asyncio.to_thread(self.p.files.put, raw); key = str(uuid4())
                media = {'id': key, 'courseId': course, 'version': '1', 'kind': 'audio', 'mime': mime, 'name': str(q.get('name', '课程录音.wav'))[:160], 'fileHash': file['hash']}
                if info:
                    media.update(durationMs=info['durationMs'], startMs=0, endMs=info['durationMs'], timelineOrigin='wav-sample-count')
                else:
                    media.update(pendingConversion=True, timelineOrigin='container-pending-decoding')
                with self.p.db.transaction():
                    if q.get('originalId'):
                        require(info, 'PCM_WAV_REQUIRED')
                        original = await self.media(course, q['originalId'], q.get('originalVersion'))
                        require(original['content'].get('pendingConversion') is True, 'ORIGINAL_ALREADY_LINKED')
                        next_version = original['revision']+1
                        self.save(course, original['id'], 'media', {**original['content'], 'version': str(next_version), 'pendingConversion': False,
                            'processingMediaId': key, 'durationMs': info['durationMs'], 'startMs': 0, 'endMs': info['durationMs'], 'timelineOrigin': 'browser-decoded-pcm'})
                        media.update(originalMediaId=original['content']['id'], originalMediaVersion=next_version)
                    result = self.save(course, 'media:'+key, 'media', media)
            elif operation in gets:
                await body(request, 1024)
                if operation == 'workspace':
                    rows = self.h.repo.all(course)
                    media_service = self.h.pages.media(course)
                    result = {'media': [r for r in rows if r['kind'] == 'media'], 'runs': [r for r in rows if r['kind'] == 'media-run'],
                        'scripts': [r for r in rows if r['kind'] == 'review-script'], 'documents': [d for d in self.p.repo.all(self.p.scope(course), 'document') if not any(d.get(k) for k in ('archived', 'superseded', 'deleted'))],
                        'parents': [{'id': r['id'], 'kind': r['kind'], 'revision': r['revision']} for r in rows if r['kind'] in ('note', 'memory-card', 'template-result')],
                        'cards': [r for r in rows if r['kind'] == 'memory-card'],
                        'voices': VOICES, 'speechConfigured': bool(self.h.app.state.config.api_key or getattr(self.h.app.state, 'learning_media_factory', None)),
                        'capabilities': {'asr': bool(media_service.asr), 'tts': bool(media_service.tts), 'image': bool(media_service.image_model)},
                        'maxAudioMs': 3600000, 'maxVideoFrames': 24, 'paidCalls': 0}
                else:
                    row = await self.get(course, q.get('id'))
                    if operation == 'result':
                        result = row
                    elif operation == 'audio':
                        require(row['kind'] == 'media-run', 'AUDIO_NOT_READY')
                        part = next((p for p in row['content']['items'] if p['id'] == q.get('part')), None)
                        require(part and part.get('audioHash'), 'AUDIO_NOT_READY')
                        return Response(self.p.files.read(part['audioHash']), media_type='audio/wav', headers={'Cache-Control': 'no-store'})
                    else:
                        require(row['kind'] == 'media-run' and row['content']['mode'] == 'synthesize' and row['content']['status'] == 'completed', 'AUDIO_NOT_READY')
                        script = await self.get(course, row['content']['scriptId'], 'review-script')
                        raw, timeline = await asyncio.to_thread(assemble_wav, row['content']['items'], self.p.files.read)
                        buffer = io.BytesIO()
                        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                            archive.writestr('review.wav', raw)
                            archive.writestr('script.json', json.dumps({'scriptVersion': row['content']['scriptRevision'], 'render': row['content'], 'currentScriptVersion': script['revision'], 'alignment': 'audio-segment'}, ensure_ascii=False, indent=2))
                            archive.writestr('script.md', '\n\n'.join(p['speaker']+': '+(p['text'] or f"[回忆留白 {p['endMs']-p['startMs']:.0f} ms]") for p in timeline))
                            archive.writestr('captions.srt', '\n\n'.join(f"{i+1}\n{srt_timestamp(p['startMs'])} --> {srt_timestamp(p['endMs'])}\n{p['speaker']}: {p['text']}" for i, p in enumerate(timeline) if p['text']))
                        return Response(buffer.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="xueya-review.zip"', 'Cache-Control': 'no-store'})
            else:
                value = await json_body(request, 1048576)
                require('courseId' not in value or value['courseId'] == course, 'COURSE_MISMATCH')
                if operation in ('prepare', 'transcribe', 'video', 'synthesize'):
                    result = await self.start(course, value, operation)
                elif operation == 'cancel':
                    row = await self.get(course, value.get('id'), 'media-run')
                    require(row['content']['status'] in ('queued', 'running'), 'MEDIA_RUN_NOT_CANCELLABLE')
                    job = self.p.jobs.cancel(row['content']['jobId'], self.p.scope_user_id)
                    c = {**row['content'], 'status': 'cancelled' if job['attempts'] == 0 else 'unknown', 'error': 'CANCELLED_CHECK_PROVIDER_OUTCOME'}
                    result = self.save(course, row['id'], 'media-run', c)
                elif operation in ('transcript/save', 'video/save'):
                    row = await self.get(course, value.get('id'), 'media-run'); c = clone(row['content'])
                    require(c['mode'] == ('transcribe' if operation == 'transcript/save' else 'video') and c['status'] == 'completed' and row['revision'] == value.get('revision'), 'ARTIFACT_CONFLICT')
                    edits = value.get('items')
                    require(value.get('confirmed') is True and isinstance(edits, list) and len(edits) == len(c['items']), 'TRANSCRIPT_REVIEW_REQUIRED')
                    for actual, edit in zip(c['items'], edits):
                        require(isinstance(edit, dict) and edit.get('id') == actual['id'] and (c['mode'] != 'video' or edit.get('timeMs') == actual['timeMs']) and isinstance(edit.get('text'), str) and 0 < len(edit['text'].strip()) <= 20000 and edit.get('reviewed') is True, 'TRANSCRIPT_REVIEW_REQUIRED')
                        actual.update(text=edit['text'], reviewed=True)
                    await self.media(course, c['mediaId'], c['mediaVersion'])
                    result = await self.h.pages.commit(course, row['id'], 'media-run', c, {**value, 'expectedRevision': row['revision']})
                elif operation == 'transcript/import':
                    result = await self.import_transcript(course, value)
                elif operation == 'transcript/link':
                    row = await self.get(course, value.get('id'), 'media-run'); c = row['content']
                    require(row['revision'] == value.get('revision') and c['mode'] in ('transcribe', 'video') and c['status'] == 'completed'
                            and all(p.get('reviewed') for p in c['items']) and value.get('confirmed') is True, 'TRANSCRIPT_REVIEW_REQUIRED')
                    original = await self.original(course, await self.media(course, c['mediaId'], c['mediaVersion']))
                    scope = self.p.scope(course)
                    doc = self.h.app.state.rag.document(scope, value.get('documentId'), active=True)
                    origin = doc.get('origin', {})
                    require(doc.get('activeArtifact') and origin.get('runId') == row['id'] and origin.get('runRevision') == row['revision'], 'TRANSCRIPT_DOCUMENT_MISMATCH')
                    with self.p.db.transaction():
                        for i, part in enumerate(c['items']):
                            key = 'library-link-'+fingerprint([doc['id'], doc.get('contentRevision'), i])[:40]
                            link = {'kind': 'library-media-link', 'documentId': doc['id'], 'documentVersion': doc['version'], 'documentContentRevision': doc.get('contentRevision'),
                                    'mediaId': original['content']['id'], 'mediaVersion': original['revision'], 'location': {'startMs': part.get('startMs', part.get('timeMs', 0)), 'endMs': part.get('endMs', min(part.get('timeMs', 0)+1, original['content']['durationMs']))}, 'confirmedByUser': True}
                            if not self.p.repo.read(scope, 'artifact', key):
                                self.p.repo.put(scope, 'artifact', key, link, 0)
                    result = {'linkedSegments': len(c['items']), 'documentId': doc['id']}
                elif operation == 'script/draft':
                    result = await self.build_script(course, value)
                elif operation == 'script/save':
                    require(value.get('confirmed') is True, 'SCRIPT_REVIEW_REQUIRED')
                    previous = await self.h.repo.get(course, identifier(value.get('id')))
                    require(not previous or previous['kind'] == 'review-script', 'ARTIFACT_KIND_CONFLICT')
                    sources = await self.h.sources({'courseId': course}, generation=False)
                    content = validate_script(value.get('content'), sources)
                    for parent in content.get('parents', []):
                        current = await self.get(course, parent['id'])
                        require(current['revision'] == parent['revision'], 'STALE_SCRIPT_PARENT')
                    for card in content.get('cardIds', []):
                        await self.get(course, card, 'memory-card')
                    result = await self.h.pages.commit(course, identifier(value.get('id')), 'review-script', content, value)
                elif operation == 'video/register':
                    media = await self.media(course, value.get('mediaId'), value.get('mediaVersion'))
                    require(media['content']['kind'] == 'video' and value.get('confirmed') is True, 'INVALID_VIDEO_SAMPLING')
                    duration = media['content'].get('durationMs')
                    frames = value.get('frames'); start, end = value.get('startMs'), value.get('endMs')
                    require(type(duration) in (int, float) and math.isfinite(duration) and type(start) in (int, float) and type(end) in (int, float)
                            and 0 <= start < end <= duration <= 1800000 and isinstance(frames, list) and 1 <= len(frames) <= 24, 'INVALID_VIDEO_SAMPLING')
                    times = []
                    for frame in frames:
                        require(isinstance(frame, dict), 'INVALID_VIDEO_FRAME')
                        m = await self.media(course, frame.get('id'), frame.get('version'))
                        require(m['content']['kind'] == 'image' and type(frame.get('timeMs')) in (int, float) and math.isfinite(frame['timeMs']) and start <= frame['timeMs'] < end, 'INVALID_FRAME_TIME')
                        times.append(frame['timeMs'])
                    require(times == sorted(set(times)), 'INVALID_FRAME_TIME')
                    result = await self.h.pages.commit(course, media['id'], 'media', {**media['content'], 'version': str(media['revision']+1),
                        'frames': frames, 'sampleRange': {'startMs': start, 'endMs': end}, 'coverage': 'sampled-frames-only', 'timelineOrigin': 'browser-sampled'}, {**value, 'expectedRevision': media['revision']})
                else:
                    raise AppError('NOT_FOUND')
            return JSONResponse({'ok': True, 'result': result})
        except (AppError, DomainError) as error:
            return JSONResponse({'ok': False, 'error': error.code}, status_code=400)
