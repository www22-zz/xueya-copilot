"""Practice HTTP surface: fixed bank, per-account state, idempotent ops, per-question notes.

Owns no model calls (PRD 15). Answers are judged locally against the built-in bank.
"""
from __future__ import annotations
import re
import secrets
from fastapi import APIRouter, Request
from .common import AppError, require
from .practice_bank import bank, question
from .practice_state import PracticeState


def install_practice(app):
    from .app import json_body, success
    router = APIRouter(prefix='/api/practice')

    def authorize(request: Request):
        require(bool(re.fullmatch(r'(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?', request.headers.get('host', ''))),
                'ORIGIN_FORBIDDEN')
        supplied = request.headers.get('origin')
        require(not supplied or supplied == str(request.base_url).rstrip('/'), 'ORIGIN_FORBIDDEN')
        require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), app.state.token), 'AUTH_REQUIRED')

    def account_id(request: Request) -> str:
        account = getattr(app.state, 'account', None)
        if account is not None and account.record():
            require(account.authorized(request), 'AUTH_REQUIRED')
            record = account.current(request)
            return (record or {}).get('learningOwner') or (record or {}).get('username') or 'local'
        return 'local'

    def store() -> PracticeState:
        host = getattr(app.state, 'practice', None)
        if host is None:
            host = PracticeState(app.state.platform)
            app.state.practice = host
        return host

    @router.get('/bank')
    async def get_bank(request: Request):
        authorize(request)
        if request.query_params.get('source') == 'workspace':
            from .practice_catalog import workspace_catalog
            return success(**workspace_catalog(app.state.practice_generation, account_id(request)))
        if request.query_params.get('courseId'):
            course = request.query_params['courseId']
            app.state.platform.repo.require_course(app.state.platform.scope(course), archived=True)
            return success(**app.state.practice_generation.catalog(account_id(request), course))
        return success(**bank())

    @router.post('/generation/{set_id}/resume')
    async def resume_generation(request: Request, set_id: str):
        authorize(request)
        return success(generation=app.state.practice_generation.resume(account_id(request), set_id))

    @router.post('/generation/{set_id}/cancel')
    async def cancel_generation(request: Request, set_id: str):
        authorize(request)
        return success(generation=app.state.practice_generation.cancel(account_id(request), set_id))

    @router.get('/state')
    async def get_state(request: Request):
        authorize(request)
        return success(**store().state(account_id(request)))

    @router.post('/ops')
    async def post_ops(request: Request):
        authorize(request)
        value = await json_body(request, 1_000_000)
        ops = value.get('ops')
        require(isinstance(ops, list) and 1 <= len(ops) <= 200, 'INVALID_OPS')
        account = account_id(request)
        generated = {q['id']: q for q in app.state.practice_generation.catalog(account, history=True)['questions']}
        from .practice_catalog import exam_bank
        generated.update({q['id']:q for q in exam_bank()['questions']})
        valid, rejected = [], []
        for op in ops:
            if not isinstance(op, dict) or (question(op.get('questionId')) is None and op.get('questionId') not in generated):
                rejected.append({'opId': op.get('opId') if isinstance(op, dict) else None, 'error': 'UNKNOWN_QUESTION'})
            else:
                try:
                    validate_written_op(op, generated)
                except AppError as error:
                    rejected.append({'opId':op.get('opId'),'error':error.code})
                    continue
                valid.append(op)
        result = store().accept(account, valid, device=str(value.get('deviceTag') or '')[:64]) if valid else {
            'accepted': [], 'duplicates': [], 'rejected': [], **store().state(account)}
        result['rejected'].extend(rejected)
        return success(**result)

    def validate_written_op(op, generated):
        if op.get('kind') == 'written-save':
            import math
            q = generated.get(op.get('questionId'))
            payload = op.get('payload')
            require(isinstance(payload,dict), 'INVALID_WRITTEN_ANSWERS')
            parts = {p['id']:p for p in (q or {}).get('parts', [])}
            answers, scores = payload.get('answers'), payload.get('scores')
            require(q and q.get('bankSource') == 'exam408' and q['type'] == 'short', 'WRITTEN_QUESTION_REQUIRED')
            require(payload.get('questionType') == 'short', 'WRITTEN_QUESTION_REQUIRED')
            require(isinstance(answers, dict) and set(answers) <= set(parts)
                    and all(isinstance(v,str) and len(v) <= 12000 for v in answers.values()), 'INVALID_WRITTEN_ANSWERS')
            require(isinstance(scores, dict) and set(scores) <= set(parts)
                    and all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= parts[k]['points'] for k,v in scores.items()), 'INVALID_SELF_SCORE')

    @router.get('/notes/{question_id}')
    async def get_note(request: Request, question_id: str):
        authorize(request)
        from .practice_catalog import exam_question
        require(question(question_id) is not None or exam_question(question_id) is not None or any(q['id'] == question_id for q in app.state.practice_generation.catalog(account_id(request), history=True)['questions']), 'UNKNOWN_QUESTION')
        return success(note=store().note(account_id(request), question_id))

    @router.get('/analysis')
    async def list_analysis(request: Request):
        authorize(request)
        return success(**app.state.practice_analysis.listing(account_id(request)))

    @router.post('/analysis')
    async def create_analysis(request: Request):
        authorize(request)
        value = await json_body(request, 16384)
        return success(job=app.state.practice_analysis.submit(account_id(request), value))

    @router.get('/analysis/sources')
    async def analysis_sources(request: Request):
        authorize(request)
        from .analysis_sources import sessions
        account=account_id(request)
        return success(sessions=[{k:r[k] for k in ('id','title','courseId','learningRelated','updatedAt')} for r in sessions(app.state.platform,account)],
            settings=app.state.analysis_schedule.read(account),candidates=app.state.analysis_schedule.listing(account))

    @router.post('/analysis/schedule')
    async def analysis_schedule(request: Request):
        authorize(request)
        return success(settings=app.state.analysis_schedule.update(account_id(request),await json_body(request,16384)))

    @router.post('/analysis/candidates/{candidate_id}/submit')
    async def candidate_analysis(request: Request,candidate_id: str):
        authorize(request)
        value=await json_body(request,4096)
        require(value.get('confirmed') is True,'CONFIRMATION_REQUIRED')
        account=account_id(request);analysis=app.state.practice_analysis;scope=analysis.scope(account)
        from .common import identifier
        with app.state.platform.db.transaction():
            row=app.state.platform.repo.read(scope,'artifact',identifier(candidate_id))
            require(row and row['value'].get('kind')=='analysis-candidate','ANALYSIS_NOT_FOUND')
            candidate=row['value']
            job=analysis.submit(account,{**candidate['snapshot']['filters'],'idempotencyKey':'candidate-'+candidate['fingerprint'][:48]},captured=candidate['snapshot'])
            candidate.update(status='submitted',jobId=job['id'])
            app.state.platform.repo.put(scope,'artifact',candidate_id,candidate,row['version'])
        return success(job=job)

    @router.get('/analysis/reports/{report_id}')
    async def read_analysis(request: Request, report_id: str):
        authorize(request)
        return success(report=app.state.practice_analysis.report(account_id(request), report_id))

    @router.post('/analysis/reports/{report_id}/chat')
    async def ask_analysis(request: Request, report_id: str):
        authorize(request)
        value = await json_body(request, 8192)
        value['reportId'] = report_id
        return success(job=app.state.practice_analysis.submit(account_id(request), value, chat=True))

    @router.get('/analysis/jobs/{job_id}')
    async def read_analysis_job(request: Request, job_id: str):
        authorize(request)
        scope = app.state.practice_analysis.scope(account_id(request))
        job = app.state.platform.jobs.get(job_id, scope.user_id)
        require(job and job['type'] in ('practice-analysis', 'practice-analysis-chat'), 'ANALYSIS_NOT_FOUND')
        return success(job=job)

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app
