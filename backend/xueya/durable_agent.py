"""Single-decision jobs using the existing learning run store and platform queue."""
import asyncio
from .evidence_review import EvidenceReviewer
import json
from uuid import uuid4
from contextlib import aclosing

from fastapi.responses import JSONResponse
from backend.core import clone, fingerprint, require
from backend.agent.http_handler import identifier
from backend.agent.orchestrator import ReadOnlyWorkflow
from backend.agent.planner import Planner
from backend.agent.tool_adapter import ReadOnlyTools, READ_ONLY_TOOLS
from .agent import normalize_request, normalize_context
from .execution_budget import budget_scope
from .learning import route_task
from .learning_integration import ScopedModel
from .mcp_core import open_session, platform_registry


class DurableAgent:
    def __init__(self, host):
        self.host, self.p, self.config = host, host.p, host.app.state.config
        self.agent = host.app.state.agent
        from .agent_interactions import AgentInteractions
        self.interactions = AgentInteractions(host)
        self.p.jobs.register('agent-step', self.execute)

    def get(self, course, key):
        row = self.p.repo.read(self.p.scope(course), 'artifact', self.host.runs.key(key))
        require(row and row['value'].get('kind') == 'dynamic-agent', 'RUN_NOT_FOUND')
        return clone(row['value'])

    def save(self, value, expected):
        scope, key = self.p.scope(value['courseId']), self.host.runs.key(value['id'])
        row = self.p.repo.read(scope, 'artifact', key)
        require((row['value']['revision'] if row else 0) == expected, 'RUN_CONFLICT')
        value = {**clone(value), 'revision': expected+1}
        self.p.repo.put(scope, 'artifact', key, value, row['version'] if row else 0)
        return value

    def enqueue(self, run):
        return self.p.jobs.submit(self.p.scope_user_id, {'type': 'agent-step', 'courseId': run['courseId'],
            'resource': 'api', 'maxAttempts': 1, 'input': {'runId': run['id']},
            'idempotencyKey': 'agent-'+fingerprint([run['id'], run['revision']])})

    def public(self, run):
        result = {k: clone(run[k]) for k in ('id', 'courseId', 'revision', 'status', 'state', 'result', 'budget', 'error', 'scenario', 'interaction') if k in run}
        result.get('state', {}).pop('tools', None)
        return result

    def features(self, course):
        bucket = int(fingerprint([self.p.scope_user_id, course])[:8], 16) % 100
        enabled = self.config.agent_planning_enabled and self.config.agent_durable_enabled and bucket < self.config.agent_rollout_percent
        return {'durable': enabled, 'interactive': enabled and self.config.agent_interactive_enabled,
            'configured': bool(self.config.api_key)}

    async def create(self, course, value):
        require(self.features(course)['durable'], 'AGENT_DISABLED')
        require(value.get('scenario', 'prepare') == 'prepare' or self.features(course)['interactive'], 'AGENT_INTERACTIVE_DISABLED')
        require(isinstance(value.get('context', {}), dict), 'INVALID_CONTEXT')
        require(identifier(value.get('id')), 'INVALID_RUN')
        request = normalize_request(value)
        # Always reload host-owned evidence; browser quotations never enter a durable run.
        library = self.agent.current_library(self.p.scope(course))
        selected = value.get('documentIds')
        require(selected is None or isinstance(selected, list) and len(selected) <= 100 and all(isinstance(s, str) for s in selected), 'INVALID_SELECTION')
        if selected is not None:
            library = [s for s in library if s.get('documentId') in selected]
        selected_sources = value.get('sourceIds')
        require(selected_sources is None or isinstance(selected_sources, list) and 0 < len(selected_sources) <= 48 and all(isinstance(s, str) for s in selected_sources), 'INVALID_SELECTION')
        if selected_sources is not None:
            library = [s for s in library if s['id'] in selected_sources]
            require(len(library) == len(set(selected_sources)), 'STALE_EVIDENCE')
        context = normalize_context({**(value.get('context') or {}), 'library': library,
            'questions': self.p.repo.all(self.p.scope(course), 'question'),
            'records': self.p.repo.all(self.p.scope(course), 'attempt')})
        request['sources'] = []
        digest = fingerprint({'request': request, 'context': context, 'scenario': value.get('scenario', 'prepare')})
        run = {'id': value['id'], 'courseId': course, 'kind': 'dynamic-agent', 'revision': 0,
            'status': 'queued', 'requestHash': digest, 'request': request, 'context': context,
            'snapshot': self.agent.evidence_snapshot(self.p.scope(course), context['library']),
            'state': {}, 'result': None, 'budget': None, 'scenario': value.get('scenario', 'prepare')}
        require(run['scenario'] in ('prepare', 'chapter', 'wrong', 'exam'), 'INVALID_SCENARIO')
        with self.p.db.transaction():
            row = await self.host.runs.get(course, run['id'])
            if row:
                require(row.get('kind') == run['kind'] and row['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
                return self.public(row)
            run = self.save(run, 0)
            self.enqueue(run)
        return self.public(run)

    async def execute(self, scope, args, **callbacks):
        course, key = scope.course_id, args['runId']
        with self.p.db.transaction():
            run = self.get(course, key)
            if run['status'] != 'queued':
                return self.public(run)
            if not self.features(course)['durable'] or run['scenario'] != 'prepare' and not self.features(course)['interactive']:
                return self.public(self.save({**run, 'status': 'paused', 'pauseRequested': True}, run['revision']))
            owner = str(uuid4())
            run = self.save({**run, 'status': 'running', 'owner': owner}, run['revision'])

        def update(**fields):
            nonlocal run
            with self.p.db.transaction():
                latest = self.get(course, key)
                require(latest.get('owner') == owner, 'RUN_CONFLICT')
                run = self.save({**latest, **fields}, latest['revision'])

        async def checkpoint(state):
            update(state=state)

        try:
            require(self.agent.evidence_current(scope, run['context']['library'], run['snapshot']), 'STALE_EVIDENCE')
            with budget_scope(self.config, fresh=True) as budget:
                if run['budget']:
                    budget.restore(run['budget'])
                budget.changed = lambda value: update(budget=value)
                registry = platform_registry(self.p, scope, context=run['context'], rag=self.agent.rag, learning=self.host)
                registry.allowed_tools = READ_ONLY_TOOLS
                async with open_session(registry, timeout=self.config.tool_timeout, max_duration=budget.remaining(), allowed_tools=READ_ONLY_TOOLS) as session:
                    tools = ReadOnlyTools(session, run['context']['library'], course_id=course,
                        verify=lambda: self.agent.evidence_current(scope, run['context']['library'], run['snapshot']))
                    flow = ReadOnlyWorkflow(Planner(ScopedModel(self.agent.model, scope), min(self.config.agent_decision_tokens, self.config.max_output_tokens)), tools,
                        max_rounds=self.config.agent_max_rounds, max_replans=self.config.agent_max_replans, max_no_progress=self.config.agent_no_progress_limit, review=EvidenceReviewer(self.agent.model, scope))
                    terminal = None
                    async with aclosing(flow.stream(run['request'], run['context'], route_task(run['request']['question'], run['request']['mode']),
                        restore=run['state'], checkpoint=checkpoint, single_step=True)) as events:
                        async for event in events:
                            if event['type'] == 'done':
                                terminal = event
                                if terminal.get('model') == 'external-planner':
                                    terminal['model'] = self.config.model
                    update(budget=budget.snapshot())
            with self.p.db.transaction():
                status = terminal['agent']['status'] if terminal else 'queued'
                if terminal and run['state'].get('phase') == 'deciding' and terminal['agent'].get('stopReason') in (
                        'AI_TIMEOUT', 'AI_INCOMPLETE', 'AI_UNAVAILABLE', 'AGENT_EXECUTION_FAILED'):
                    status = 'unknown'
                fields = {}
                if status == 'completed' and run['scenario'] != 'prepare':
                    fields = await self.interactions.prepare({**run, 'result': terminal})
                    status = fields.pop('status')
                update(**fields, status='paused' if run.get('pauseRequested') and not terminal else status,
                    result=terminal, state={**run['state'], **(terminal['agent'] if terminal else {})}, owner=None)
                if run['status'] == 'queued':
                    self.enqueue(run)
            return self.public(run)
        except (Exception, asyncio.CancelledError) as error:
            # The model reservation and deciding marker were committed before transport.
            phase = run.get('state', {}).get('phase')
            update(status='unknown' if phase == 'deciding' else 'failed', error=getattr(error, 'code', 'AGENT_INTERRUPTED'), owner=None)
            if isinstance(error, asyncio.CancelledError):
                raise
            return self.public(run)

    async def control(self, course, key, action, body):
        with self.p.db.transaction():
            run = self.get(course, key)
            require(body.get('revision') == run['revision'], 'RUN_CONFLICT')
            if action in ('confirm', 'answer', 'refresh', 'diagnose', 'replan'):
                require(self.features(course)['interactive'], 'AGENT_INTERACTIVE_DISABLED')
                require(self.agent.evidence_current(self.p.scope(course), run['context']['library'], run['snapshot']), 'STALE_EVIDENCE')
                require(run['scenario'] != 'prepare' and (run['status'] in ('awaiting_user', 'awaiting_confirmation') or
                    action == 'replan' and run['status'] == 'completed'), 'RUN_NOT_RESUMABLE')
                fields = await self.interactions.act(run, action, body)
                run = self.save({**run, **fields}, run['revision'])
                return self.public(run)
            if action == 'pause':
                require(run['status'] in ('queued', 'running'), 'RUN_NOT_PAUSABLE')
                run = self.save({**run, 'pauseRequested': True,
                    'status': 'paused' if run['status'] == 'queued' else 'running'}, run['revision'])
            elif action == 'cancel':
                require(run['status'] != 'running', 'RUN_BUSY_PAUSE_FIRST')
                run = self.save({**run, 'status': 'cancelled'}, run['revision'])
            elif action == 'resume':
                require(self.features(course)['durable'], 'AGENT_DISABLED')
                require(run['status'] in ('paused', 'awaiting_user', 'unknown', 'failed'), 'RUN_NOT_RESUMABLE')
                require(not run.get('interaction'), 'USE_LEARNING_INTERACTION')
                require(run['status'] != 'unknown' or body.get('acknowledgeUnknown') is True, 'UNKNOWN_OUTCOME_CONFIRMATION_REQUIRED')
                if run['status'] == 'awaiting_user':
                    require(isinstance(body.get('userInput'), str) and 0 < len(body['userInput']) <= 2000, 'USER_INPUT_REQUIRED')
                    run['request']['history'] = (run['request']['history']+[{'role': 'user', 'content': body['userInput']}])[-8:]
                run['state']['noProgress'] = 0
                run = self.save({**run, 'status': 'queued', 'pauseRequested': False, 'error': None}, run['revision'])
                self.enqueue(run)
            else:
                require(False, 'INVALID_ACTION')
        return self.public(run)

    async def recover(self):
        for course in self.p.repo.courses(self.p.scope_user_id):
            if course['archived']:
                continue
            for run in self.host.runs.all(course['id']):
                if run.get('kind') != 'dynamic-agent':
                    continue
                with self.p.db.transaction():
                    if run['status'] == 'running':
                        self.save({**run, 'status': 'unknown', 'owner': None, 'error': 'PROCESS_INTERRUPTED'}, run['revision'])
                    elif run['status'] == 'queued':
                        self.enqueue(run)

    async def dispatch(self, path, request, course):
        if not path.startswith('agent-runs'):
            return None
        parts = path.split('/')
        if path == 'agent-runs/features' and request.method == 'GET':
            return JSONResponse({'ok': True, 'result': self.features(course)})
        if request.method == 'GET' and len(parts) == 2:
            result = self.public(self.get(course, parts[1]))
        else:
            require(request.method == 'POST', 'METHOD_NOT_ALLOWED')
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                require(len(raw) <= 131072, 'REQUEST_TOO_LARGE')
            try:
                body = json.loads(raw)
            except ValueError:
                require(False, 'INVALID_JSON')
            require(isinstance(body, dict) and body.get('courseId', course) == course, 'COURSE_MISMATCH')
            if len(parts) == 1:
                result = await self.create(course, body)
            else:
                require(len(parts) == 3, 'ROUTE_NOT_FOUND')
                result = await self.control(course, parts[1], parts[2], body)
        return JSONResponse({'ok': True, 'result': result})
