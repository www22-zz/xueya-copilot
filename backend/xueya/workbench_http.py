"""Safe, additive projections of the host's capabilities, jobs and API ledger."""
import json
import re
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from .common import require, utc_now


def capabilities(app):
    config, rag = app.state.config, app.state.rag
    # Never return credentials, endpoints, file contents or Config's repr.
    from backend.providers.mimo import MODELS
    image = bool(config.api_key and MODELS.get(config.model, {}).get('image'))
    values = [('text', '文字与课程学习', bool(config.api_key), config.model, 'MIMO'),
              ('image', '图片理解', image, config.model, 'MIMO'),
              ('asr', '录音转写', bool(config.api_key), 'mimo-v2.5-asr', 'MIMO'),
              ('tts', '语音讲解', bool(config.api_key), 'mimo-v2.5-tts', 'MIMO')]
    for name, label in [('embedding', '向量检索'), ('rerank', '检索重排'), ('ocr', '扫描件识别')]:
        provider = getattr(rag, name, None)
        values.append((name, label, bool(provider and provider.settings.key), provider.settings.model if provider else '', 'RAG_'+name.upper()))
    return [{'id': name, 'label': label, 'configured': configured, 'model': model,
             'status': 'configured_unverified' if configured else 'unconfigured',
             'connectionVerified': False, 'configurationPrefix': prefix,
             'note': '已有配置；尚无本中心的真实连接验证' if configured else '未配置；可在 .env 中配置并重启'}
            for name, label, configured, model, prefix in values]


SAFE_LOCAL_JOBS = frozenset(('rag-parse', 'parse-document', 'library-web-import'))


def task_projection(p, learning, course, all_courses=False):
    courses = {c['id']: c for c in p.repo.courses(p.user_id)}
    require(course in courses, 'COURSE_NOT_FOUND')
    jobs = [j for j in p.jobs.list(p.user_id) if all_courses or j['courseId'] == course]
    tasks = []
    for j in jobs:
        safe_retry = j['resource'] == 'cpu' and j['type'] in SAFE_LOCAL_JOBS and j['status'] in ('failed', 'cancelled')
        tasks.append({k: j[k] for k in ('id', 'courseId', 'type', 'status', 'attempts', 'resource', 'createdAt', 'updatedAt')} |
                     {'canCancel': j['status'] in ('queued', 'running', 'cancelling'), 'canRetry': safe_retry,
                      'hasCheckpoint': bool(j['checkpoint']), 'hasResult': j['result'] is not None,
                      'progress': j['progress'].get('percent') if isinstance(j['progress'], dict) and isinstance(j['progress'].get('percent'), (int, float)) else None,
                      'message': '远端结果不明，请先核对用量与产物；不会自动重试。' if j['status'] == 'unknown' else
                                 '处理失败，请检查资料或服务设置。' if j['status'] == 'failed' else '',
                      'destination': 'library' if j['type'].startswith(('rag-', 'parse-', 'library-')) else 'overview'})
    pending = []
    if learning:
        for cid, c in courses.items():
            if c['archived'] or not all_courses and cid != course:
                continue
            for run in learning.runs.all(cid):
                if run.get('status') in ('awaiting_confirmation', 'awaiting_user', 'unknown', 'failed', 'queued', 'running'):
                    pending.append({'id': run['id'], 'courseId': cid, 'status': run['status'], 'revision': run['revision'],
                                    'updatedAt': run.get('updatedAt'), 'destination': 'overview'})
    rows = p.db.all('SELECT id,course_id,status,usage_json,billing_status,at FROM invocations WHERE user_id=? '+
                    ('' if all_courses else 'AND course_id=? ')+ 'ORDER BY at DESC LIMIT 100',
                    (p.user_id,) if all_courses else (p.user_id, course))
    calls = []
    for row in rows:
        usage = json.loads(row['usage_json']) if row['usage_json'] else None
        # Suppliers can return arbitrary payloads: expose numeric usage units only.
        usage = {k: v for k, v in (usage if isinstance(usage, dict) else {}).items() if re.fullmatch(r'[a-zA-Z_]{1,50}', k) and type(v) in (int, float) and v >= 0}
        calls.append({'id': row['id'], 'courseId': row['course_id'], 'status': row['status'], 'at': row['at'],
                      'usage': usage or None, 'billingStatus': row['billing_status']})
    return {'tasks': tasks, 'pending': pending[:100], 'invocations': calls, 'limit': 100,
            'usageScope': '最近100条调用，非完整账单', 'currencyEstimate': None}


def install_workbench(app):
    router = APIRouter(prefix='/api/platform/workbench')

    @router.api_route('/{operation}', methods=['GET', 'POST'])
    async def route(operation: str, request: Request):
        require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), app.state.token), 'AUTH_REQUIRED')
        p = app.state.platform
        require(p is not None, 'PLATFORM_DISABLED')
        from .app import json_body, success
        value = await json_body(request) if request.method == 'POST' else {}
        course = request.query_params.get('courseId') or value.get('courseId') or 'course-default'
        p.repo.require_course(p.scope(course), archived=True)
        if operation == 'capabilities' and request.method == 'GET':
            return success(capabilities=capabilities(app), credentialStorage='env-only', paidTestsEnabled=False,
                           fallback='向量未配置时使用词法检索；配置状态不等于模型质量验证。')
        if operation == 'check' and request.method == 'POST':
            require(not set(value)-{'courseId', 'mode'} and value.get('mode', 'local') == 'local', 'PAID_TEST_NOT_AUTHORIZED')
            url = urlsplit(app.state.config.base_url)
            valid = url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password and not url.query and not url.fragment
            return success(checkedAt=utc_now(), mode='local', networkRequests=0, connectionVerified=False,
                           configurationValid=valid, error=None if valid else 'INVALID_PROVIDER_URL', capabilities=capabilities(app))
        if operation == 'tasks' and request.method == 'GET':
            return success(**task_projection(p, app.state.learning, course, request.query_params.get('scope') == 'all'))
        if operation == 'task-action' and request.method == 'POST':
            job = p.jobs.get(value.get('id'), p.user_id)
            require(job and job['courseId'] == course, 'JOB_NOT_FOUND')
            require(value.get('action') in ('cancel', 'retry'), 'INVALID_TASK_ACTION')
            if value['action'] == 'retry':
                require(job['resource'] == 'cpu' and job['type'] in SAFE_LOCAL_JOBS and job['status'] in ('failed', 'cancelled'), 'JOB_NOT_SAFE_TO_RETRY')
            job = (p.jobs.cancel if value['action'] == 'cancel' else p.jobs.retry)(job['id'], p.user_id)
            return success(id=job['id'], status=job['status'])
        require(False, 'NOT_FOUND')

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
