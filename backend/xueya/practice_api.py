"""Practice HTTP surface: fixed bank, per-account state, idempotent ops, per-question notes.

Owns no model calls (PRD 15). Answers are judged locally against the built-in bank.
"""
from __future__ import annotations
import re
import secrets
from fastapi import APIRouter, Request
from .common import require
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
            return (record or {}).get('username') or 'local'
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
        return success(**bank())

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
        valid, rejected = [], []
        for op in ops:
            if not isinstance(op, dict) or question(op.get('questionId')) is None:
                rejected.append({'opId': op.get('opId') if isinstance(op, dict) else None, 'error': 'UNKNOWN_QUESTION'})
            else:
                valid.append(op)
        account = account_id(request)
        result = store().accept(account, valid, device=str(value.get('deviceTag') or '')[:64]) if valid else {
            'accepted': [], 'duplicates': [], 'rejected': [], **store().state(account)}
        result['rejected'].extend(rejected)
        return success(**result)

    @router.get('/notes/{question_id}')
    async def get_note(request: Request, question_id: str):
        authorize(request)
        require(question(question_id) is not None, 'UNKNOWN_QUESTION')
        return success(note=store().note(account_id(request), question_id))

    @router.get('/analysis')
    async def list_analysis(request: Request):
        authorize(request)
        return success(**app.state.practice_analysis.listing(account_id(request)))

    @router.post('/analysis')
    async def create_analysis(request: Request):
        authorize(request)
        value = await json_body(request, 4096)
        return success(job=app.state.practice_analysis.submit(account_id(request), value))

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
