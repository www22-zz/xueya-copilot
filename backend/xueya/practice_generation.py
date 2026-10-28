"""Document-grounded 100+100 banks, using the existing question domain and durable API queue."""
from __future__ import annotations
import re
from uuid import uuid4

from backend.agent.question_service import QuestionService
from backend.core import DomainError
from .common import AppError, Scope, digest, require, utc_now
from .practice_state import PracticeState
from .rag_api import borrowed_api_permit

JOB = 'practice-generate'
BATCH = 5
TARGET = 200
ACTIVE = ('queued', 'running', 'cancelling')
CODING = re.compile(r'```(?:python|java|cpp|c\+\+|c\b|javascript|js\b|sql)|\b(?:def\s+\w+\(|public\s+(?:static|class)|SELECT\s+.+?FROM|printf\s*\(|return\s+\w+\s*;)|编程|程序设计|数据结构|算法实现|代码实现', re.I)


class PracticeGeneration:
    def __init__(self, app):
        self.p, self.rag = app.state.platform, app.state.rag
        self.provider, self.config = app.state.provider, app.state.config
        self.state = PracticeState(self.p)
        from .curated_practice import CuratedPractice
        self.curated = CuratedPractice(self.p, self.rag)
        self.p.jobs.register(JOB, self.execute)
        self.rag.on_publish = self.document_ready

    def read(self, account, set_id):
        scope = self.state.scope(account)
        row = self.p.repo.read(scope, 'artifact', set_id)
        require(row and row['value'].get('kind') == JOB, 'PRACTICE_SET_NOT_FOUND')
        return row['value']

    def save(self, account, value):
        self.p.repo.put(self.state.scope(account), 'artifact', value['id'], value)

    def watch(self, account, source_scope, document_id):
        """Only user material uploads opt in; demo/CLI imports never start paid generation."""
        doc = self.rag.document(source_scope, document_id, active=True)
        set_id = 'practice-set-' + digest([account, source_scope.wire(), document_id])[:32]
        with self.p.db.transaction():
            if self.p.repo.read(self.state.scope(account), 'artifact', set_id):
                return self.summary(account, self.read(account, set_id))
            value = {'id': set_id, 'kind': JOB, 'account': account, 'courseId': source_scope.course_id,
                     'sourceScope': source_scope.wire(), 'documentId': document_id, 'name': doc['name'],
                     'status': 'waiting_parse', 'revision': 0, 'questions': [], 'batch': 0,
                     'createdAt': utc_now(), 'jobId': None}
            self.save(account, value)
            marker_id = 'practice-watch-' + document_id
            marker = self.p.repo.read(source_scope, 'artifact', marker_id)
            watchers = (marker['value'].get('watchers', []) if marker else []) + [{'account': account, 'setId': set_id}]
            self.p.repo.put(source_scope, 'artifact', marker_id, {'watchers': watchers})
            if doc.get('contentRevision'):
                self.document_ready(source_scope, {'documentId': document_id})
            return self.summary(account, self.read(account, set_id))

    def document_ready(self, scope, result):
        marker = self.p.repo.read(scope, 'artifact', 'practice-watch-' + result['documentId'])
        if not marker:
            return
        doc = self.rag.document(scope, result['documentId'], active=True)
        for watcher in marker['value']['watchers']:
            value = self.read(watcher['account'], watcher['setId'])
            if value['status'] not in ('waiting_parse', 'insufficient_material', 'model_unavailable'):
                continue
            sources = self.rag.sources(scope, document_ids=[doc['id']])
            value.update(revision=doc['contentRevision'], status='ready_to_generate')
            if sum(len(s.get('quote', '')) for s in sources) < 800:
                value.update(status='insufficient_material', error='PRACTICE_INSUFFICIENT_MATERIAL')
            elif not self.config.api_key:
                value.update(status='model_unavailable', error='AI_UNAVAILABLE')
            else:
                value['coding'] = bool(CODING.search('\n'.join(s['quote'] for s in sources)))
                self.enqueue(value)
            self.save(watcher['account'], value)

    def enqueue(self, value):
        scope = self.state.scope(value['account'])
        job = self.p.jobs.submit(scope.user_id, {'type': JOB, 'courseId': scope.course_id, 'resource': 'api',
            'maxAttempts': 1, 'idempotencyKey': 'practice-' + str(uuid4()),
            'input': {'setId': value['id'], 'batch': value['batch']}})
        value.update(status='generating', jobId=job['id'], error=None)

    def summary(self, account, value):
        result = {k: value.get(k) for k in ('id', 'courseId', 'documentId', 'name', 'status', 'revision', 'jobId', 'error')}
        result['completed'] = len(value['questions'])
        result['target'] = TARGET
        if value['status'] == 'waiting_parse':
            rows = self.p.db.all("SELECT id,input FROM jobs WHERE user_id=? AND course_id=? AND type='rag-parse' ORDER BY created_at DESC",
                                 (value['sourceScope']['userId'], value['courseId']))
            import json
            for row in rows:
                if json.loads(row['input']).get('documentId') == value['documentId']:
                    parsed = self.p.jobs.get(row['id'], value['sourceScope']['userId'])
                    if parsed['status'] in ('failed', 'cancelled', 'unknown'):
                        result.update(status=parsed['status'], error=parsed['error'])
                    break
        job = self.p.jobs.get(value.get('jobId'), self.state.scope(account).user_id) if value.get('jobId') else None
        if value['status'] == 'generating' and job and job['status'] not in ACTIVE and job['status'] != 'succeeded':
            result.update(status=job['status'], error=job['error'])
        return result

    def sets(self, account, course_id=None):
        values = [v for v in self.p.repo.all(self.state.scope(account), 'artifact')
                  if v.get('kind') == JOB and (course_id is None or v['courseId'] == course_id)]
        return sorted(values, key=lambda v: (v['createdAt'], v['id']))

    def catalog(self, account, course_id=None, *, history=False):
        questions, summaries = [], []
        for value in self.sets(account, course_id):
            summary = self.summary(account, value)
            if history and value['status'] == 'succeeded':
                questions.extend(value['questions'])
                summaries.append(summary)
                continue
            try:
                doc = self.rag.document(Scope(**value['sourceScope']), value['documentId'], active=not history)
                if not history and value['revision'] and doc.get('contentRevision') != value['revision']:
                    summary['status'] = 'stale'
                elif value['status'] == 'succeeded':
                    questions.extend(value['questions'])
            except AppError:
                summary['status'] = 'stale'
            summaries.append(summary)
        curated = self.curated.catalog(course_id, history=history)
        if history:
            known = {q['id'] for q in questions}
            questions.extend(q for q in curated['questions'] if q['id'] not in known)
            summaries.extend(curated['generations'])
        elif curated['generations']:
            questions = curated['questions']
            summaries = curated['generations']
        return {'version': 'documents-' + digest([[[s['id'], s['status'], s['completed']] for s in summaries], curated['version']])[:24],
                'questions': questions, 'generations': summaries, 'available': bool(self.config.api_key)}

    def resume(self, account, set_id):
        with self.p.db.transaction():
            value = self.read(account, set_id)
            summary = self.summary(account, value)
            require(summary['status'] not in ACTIVE + ('generating', 'succeeded', 'waiting_parse'), 'PRACTICE_GENERATION_BUSY')
            require(bool(self.config.api_key), 'AI_UNAVAILABLE')
            scope = Scope(**value['sourceScope'])
            doc = self.rag.document(scope, value['documentId'], active=True)
            require(doc.get('contentRevision') == value['revision'], 'PRACTICE_SOURCE_CHANGED')
            sources = self.rag.sources(scope, document_ids=[doc['id']])
            require(sum(len(s['quote']) for s in sources) >= 800, 'PRACTICE_INSUFFICIENT_MATERIAL')
            value['coding'] = bool(CODING.search('\n'.join(s['quote'] for s in sources)))
            self.enqueue(value)
            self.save(account, value)
            return self.summary(account, value)

    def cancel(self, account, set_id):
        with self.p.db.transaction():
            value = self.read(account, set_id)
            if value.get('jobId'):
                self.p.jobs.cancel(value['jobId'], self.state.scope(account).user_id)
            return self.summary(account, value)

    async def execute(self, scope, args, *, progress, checkpoint, commit):
        account = scope.user_id.removeprefix('practice:')
        value = self.read(account, args.get('setId'))
        require(value['batch'] == args.get('batch') and value['status'] == 'generating', 'NOT_SENT')
        from .invocation_context import active_job
        context = active_job.get() or {}
        row = self.p.db.one('SELECT resource,max_attempts FROM jobs WHERE id=?', (context.get('id'),))
        require(context.get('id') == value['jobId'] and row and row['resource'] == 'api' and row['max_attempts'] == 1, 'NOT_SENT')
        source_scope = Scope(**value['sourceScope'])
        doc = self.rag.document(source_scope, value['documentId'], active=True)
        require(doc['contentRevision'] == value['revision'], 'PRACTICE_SOURCE_CHANGED')
        sources = self.rag.sources(source_scope, document_ids=[doc['id']])
        category = 'hot100' if len(value['questions']) < 100 else 'basic'
        kinds = ['single', 'multiple', 'fill', 'boolean'] + (['code'] if value['coding'] else [])
        kind = kinds[value['batch'] % len(kinds)]
        count = min(2 if kind == 'code' else BATCH, 100 - len(value['questions']) % 100)
        if kind == 'code':
            sources = [source for source in sources if CODING.search(source['quote'])]
            require(sources, 'PRACTICE_NO_CODE_EVIDENCE')
        # Each batch advances through the whole document, with nearby context.
        offset = (value['batch'] % 20) * len(sources) // 20
        selected = [sources[(offset+i) % len(sources)] for i in range(min(3, len(sources)))]
        evidence = [{'id': s['id'], 'courseId': value['courseId'], 'documentId': doc['id'],
                     'version': str(value['revision']), 'quote': s['quote'][:6000], 'location': s.get('location', '')} for s in selected]
        progress({'label': f'正在生成{"经典重点" if category == "hot100" else "基础"}题', 'completed': len(value['questions']), 'target': TARGET})
        owner = self

        class Adapter:
            async def generate(self, request):
                with borrowed_api_permit(owner.p):
                    try:
                        return await owner.provider.generate(request['messages'], scope=scope, timeout=70,
                            max_output_tokens=owner.config.max_output_tokens,
                            response_format={'type': 'json_object'}, thinking={'type': 'disabled'})
                    except (AppError, TimeoutError):
                        raise
                    except Exception as error:
                        raise AppError('AI_UNAVAILABLE') from error

        try:
            generated = await QuestionService(model=Adapter()).generate({'courseId': value['courseId'], 'sources': evidence,
                'count': count, 'types': [kind], 'existing': value['questions'],
                'practiceProfile': {'category': category, 'document': value['name'], 'codingAllowed': value['coding'],
                                    'goal': '经典重点与综合应用' if category == 'hot100' else '基本概念与直接应用'}})
        except DomainError as error:
            raise AppError(error.code) from error
        require(len(generated['questions']) == count, 'PRACTICE_BATCH_INCOMPLETE')
        output = []
        for i, q in enumerate(generated['questions']):
            require(q['type'] != 'multiple' or len(q['answer']) >= 2, 'PRACTICE_INVALID_MULTIPLE')
            require(q['type'] != 'fill' or len(q['answers']) == 1, 'PRACTICE_SINGLE_BLANK_REQUIRED')
            converted = {**q, 'id': 'g-' + digest([value['id'], len(value['questions'])+i])[:32],
                'number': (len(value['questions'])+i) % 100 + 1,
                'category': category, 'subject': value['name'].rsplit('.', 1)[0], 'topic': doc.get('chapter') or '资料重点',
                'title': q['prompt'][:60], 'tags': [doc.get('chapter') or '资料重点'],
                'documentId': doc['id'], 'documentName': value['name'], 'generated': True,
                'difficulty': ({'easy': '简单', 'medium': '中等', 'hard': '困难'} if category == 'hot100' else
                               {'easy': '基础', 'medium': '进阶', 'hard': '挑战'})[q['difficulty']]}
            if q['type'] == 'fill':
                converted.update(answer=q['answers'][0][0], acceptedAnswers=q['answers'][0])
            output.append(converted)

        def publish():
            current_doc = self.rag.document(source_scope, doc['id'], active=True)
            require(current_doc['contentRevision'] == value['revision'], 'PRACTICE_SOURCE_CHANGED')
            value['questions'].extend(output)
            value['batch'] += 1
            if len(value['questions']) == TARGET:
                require(all(sum(q['category'] == c for q in value['questions']) == 100 for c in ('hot100', 'basic')), 'PRACTICE_INVALID_COUNTS')
                value.update(status='succeeded', completedAt=utc_now())
            else:
                self.enqueue(value)
            self.save(account, value)
        commit(publish)
        return {'setId': value['id'], 'completed': len(value['questions']), 'target': TARGET}
