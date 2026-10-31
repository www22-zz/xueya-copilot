"""Main-platform jobs and account-scoped report storage for AI practice analysis."""
from __future__ import annotations
import json
from uuid import uuid4

from backend.agent.practice_analysis import build_snapshot, filters, report_messages, validate_report, SYSTEM
from .common import AppError, dumps, identifier, require, utc_now
from .practice_bank import bank
from .practice_state import PracticeState
from .rag_api import borrowed_api_permit

REPORT_JOB = 'practice-analysis'
CHAT_JOB = 'practice-analysis-chat'
ACTIVE = ('queued', 'running', 'cancelling')


class PracticeAnalysis:
    def __init__(self, platform, provider, config):
        self.p, self.provider, self.config = platform, provider, config
        self.practice = PracticeState(platform)
        platform.jobs.register(REPORT_JOB, self.execute_report)
        platform.jobs.register(CHAT_JOB, self.execute_chat)

    def scope(self, account):
        return self.practice.scope(account)

    def report(self, account, report_id):
        identifier(report_id)
        row = self.p.repo.read(self.scope(account), 'artifact', report_id)
        require(row and row['value'].get('kind') == REPORT_JOB, 'ANALYSIS_NOT_FOUND')
        return row['value']

    def listing(self, account):
        scope = self.scope(account)
        # Bound history on the server; full reports are fetched only when selected.
        rows = self.p.db.all("SELECT data FROM entities WHERE user_id=? AND course_id=? AND kind='artifact' AND id LIKE 'analysis-%' AND deleted=0 ORDER BY created_at DESC LIMIT 30",
                             (scope.user_id, scope.course_id))
        reports = []
        for row in rows:
            report = json.loads(row['data'])
            if report.get('kind') == REPORT_JOB:
                reports.append({key: report[key] for key in ('id', 'createdAt', 'filters', 'title', 'cutoff', 'serverSeq')})
        jobs = [job for job in self.p.jobs.list(scope.user_id) if job['type'] in (REPORT_JOB, CHAT_JOB)]
        return {'reports': reports, 'jobs': jobs[:20], 'available': bool(self.config.api_key)}

    def prior(self, scope, job_type, key, request):
        identifier(key)
        row = self.p.db.one('SELECT id,input FROM jobs WHERE user_id=? AND course_id=? AND type=? AND idempotency_key=?',
                            (scope.user_id, scope.course_id, job_type, key))
        if row:
            require(json.loads(row['input'])['request'] == request, 'IDEMPOTENCY_CONFLICT')
            return self.p.jobs.get(row['id'], scope.user_id)
        return None

    def capture(self, account, request, now=None, window_start=None):
        from .analysis_sources import enrich, source_options
        scope=self.scope(account)
        generated=getattr(self,'generated_catalog',lambda account:[])(account)
        snapshot=build_snapshot(bank()['questions']+generated,self.practice.events(scope),self.practice.state(account),request,now,window_start)
        snapshot=enrich(self.p,account,snapshot,source_options(request))
        snapshot['filters']=request
        return snapshot

    def submit(self, account, value, *, chat=False, captured=None):
        scope = self.scope(account)
        job_type = CHAT_JOB if chat else REPORT_JOB
        key = value.get('idempotencyKey')
        if chat:
            message = value.get('message')
            require(isinstance(message, str) and 0 < len(message.strip()) <= 1000, 'INVALID_ANALYSIS_MESSAGE')
            request = {'reportId': value.get('reportId'), 'message': message.strip()}
            report = self.report(account, request['reportId'])
        else:
            request = filters(value)
            from .analysis_sources import source_options
            request.update(source_options(value))
        # Idempotency and the one-active-job rule share the same SQLite transaction.
        with self.p.db.transaction():
            existing = self.prior(scope, job_type, key, request)
            if existing:
                return existing
            snapshot_key=None
            if not chat:
                from .analysis_sources import content_fingerprint
                snapshot=captured or self.capture(account,request)
                require(snapshot['stats']['practicedQuestions']>0 or snapshot['hasNonPracticeActivity'],'ANALYSIS_NO_RECORDS')
                snapshot_key=content_fingerprint(snapshot)
                old=self.p.db.one("SELECT id FROM jobs WHERE user_id=? AND course_id=? AND type=? AND json_extract(input,'$.snapshotKey')=? ORDER BY created_at LIMIT 1",(scope.user_id,scope.course_id,REPORT_JOB,snapshot_key))
                if old:
                    prior_job=self.p.jobs.get(old['id'],scope.user_id)
                    require(prior_job['status'] not in ACTIVE,'ANALYSIS_BUSY')
                    return prior_job
            require(bool(self.config.api_key), 'AI_UNAVAILABLE')
            active = self.p.db.one("SELECT id FROM jobs WHERE user_id=? AND type IN (?,?) AND status IN ('queued','running','cancelling')",
                                   (scope.user_id, REPORT_JOB, CHAT_JOB))
            require(not active, 'ANALYSIS_BUSY')
            if chat:
                args = {'request': request, 'snapshot': report['snapshot'], 'report': report['analysis'],
                        'conversation': report.get('conversation', [])[-6:]}
            else:
                args = {'request': request, 'snapshot': snapshot, 'snapshotKey':snapshot_key,'reportId': 'analysis-' + str(uuid4())}
            return self.p.jobs.submit(scope.user_id, {'type': job_type, 'courseId': scope.course_id, 'input': args,
                                                      'resource': 'api', 'maxAttempts': 1, 'idempotencyKey': key})

    async def generate(self, scope, messages, *, structured=False):
        # The leased job already holds the platform's API slot.
        with borrowed_api_permit(self.p):
            try:
                return await self.provider.generate(messages, scope=scope, timeout=70,
                    max_output_tokens=min(self.config.max_output_tokens, 3200 if structured else 1800),
                    thinking={'type': 'disabled'},
                    **({'response_format': {'type': 'json_object'}} if structured else {}))
            except (AppError, TimeoutError):
                raise
            except Exception as error:
                # Provider/transport exceptions must never leak credentials in job errors.
                raise AppError('AI_UNAVAILABLE') from error

    async def execute_report(self, scope, args, *, progress, checkpoint, commit):
        snapshot = args['snapshot']
        progress({'label': 'AI 正在分析真实练习记录', 'reportId': args['reportId']})
        result = await self.generate(scope, report_messages(snapshot), structured=True)
        analysis = validate_report(result['content'], snapshot)
        report = {'id': args['reportId'], 'kind': REPORT_JOB, 'createdAt': utc_now(),
                  'filters': snapshot['filters'], 'cutoff': snapshot['cutoff'], 'serverSeq': snapshot['serverSeq'],
                  'title': analysis['title'], 'analysis': analysis, 'snapshot': snapshot,
                  'model': result.get('model', self.config.model), 'conversation': []}
        commit(lambda: self.p.repo.put(scope, 'artifact', report['id'], report))
        return {'reportId': report['id']}

    async def execute_chat(self, scope, args, *, progress, checkpoint, commit):
        progress({'label': 'AI 正在结合报告回答追问', 'reportId': args['request']['reportId']})
        messages = [{'role': 'system', 'content': SYSTEM.split('返回纯JSON对象')[0] + '\n本轮直接用中文普通文本回答追问，最多800字。明确报告截止日期，不声称读取了新的记录。'},
                    {'role': 'user', 'content': dumps({'snapshot': args['snapshot'], 'report': args['report']})}]
        messages.extend({'role': row['role'], 'content': row['content']} for row in args['conversation'])
        messages.append({'role': 'user', 'content': args['request']['message']})
        result = await self.generate(scope, messages)
        answer = result.get('content')
        require(isinstance(answer, str) and 0 < len(answer.strip()) <= 8000, 'ANALYSIS_INVALID_RESPONSE')
        report_id = args['request']['reportId']

        def save():
            stored = self.p.repo.read(scope, 'artifact', report_id)
            require(stored and stored['value'].get('kind') == REPORT_JOB, 'ANALYSIS_NOT_FOUND')
            report = stored['value']
            report['conversation'] = (report.get('conversation', []) + [
                {'role': 'user', 'content': args['request']['message'], 'at': utc_now()},
                {'role': 'assistant', 'content': answer.strip(), 'at': utc_now()}])[-30:]
            self.p.repo.put(scope, 'artifact', report_id, report, stored['version'])
        commit(save)
        return {'reportId': report_id}
