"""Bounded plan/act/observe loop. Business writes and durable resume are excluded."""
import asyncio
import re
from ..core import require, clone, check_cancel
from .planner import validate_plan
from .result_evaluator import ResultEvaluator
from .tool_adapter import TOOL_LABELS

FATAL_CODES = frozenset(('STALE_EVIDENCE', 'RESULT_SCOPE_MISMATCH', 'MCP_INVALID_RESULT',
    'AI_MODEL_BUDGET_EXCEEDED', 'AI_TOOL_BUDGET_EXCEEDED', 'AI_OUTPUT_BUDGET_EXCEEDED',
    'AI_COST_BUDGET_EXCEEDED', 'AI_PRICING_REQUIRED', 'AI_RUN_TIMEOUT',
    'AI_TRUNCATED', 'AI_INCOMPLETE', 'AI_UNAVAILABLE', 'AI_TIMEOUT', 'API_BUSY'))


class ReadOnlyWorkflow:
    def __init__(self, planner, tools, *, max_rounds=8, max_replans=2, max_no_progress=2):
        self.planner, self.tools = planner, tools
        self.max_rounds, self.max_replans, self.max_no_progress = max_rounds, max_replans, max_no_progress

    async def stream(self, request, context, intent, signal=None):
        plan, completed, observations, decisions, revisions = None, set(), [], [], []
        rounds, replans, no_progress = 0, 0, 0
        evaluator = ResultEvaluator(request, context, self.tools, intent)
        catalogue = await self.tools.catalogue()
        require(catalogue, 'MCP_TOOL_MISSING')

        def state(status='running', reason=None):
            return {'status': status, 'planRevision': len(revisions), 'plan': clone(plan),
                    'planHistory': clone(revisions), 'completedStepIds': sorted(completed),
                    'observations': clone(observations[-8:]), 'decisions': clone(decisions),
                    'decisionCount': rounds, 'replans': replans, 'stopReason': reason,
                    'scope': 'read-only-request', 'persistedResume': False}

        def event(stage, label, status='running'):
            return {'type': 'workflow', 'stage': stage, 'label': label, 'status': status, 'agent': state()}

        async def terminal(status, reason, answer=None, question=None):
            check_cancel(signal)
            await self.tools.current()
            value = await evaluator.render(answer)
            if question:
                value['answer'] += '\n\n需要你补充信息才能继续：'+question
            elif status != 'completed':
                value['answer'] += '\n\n本轮只读准备尚未全部完成。请补充条件或资料后继续。'
            value['answer'] = value['answer'][:16000]
            return {'type': 'done', **value, 'agent': state(status, reason)}

        yield event('plan', '正在根据学习目标制定执行计划')
        try:
            for rounds in range(1, self.max_rounds+1):
                check_cancel(signal)
                await self.tools.current()
                decision = await self.planner.decide({'request': {'question': request['question'], 'mode': request['mode'],
                    'history': [{**m, 'content': m['content'][:2000]} for m in request['history'][-4:]]},
                    'context': {k: context[k] for k in ('baseDate', 'examDate', 'minutes', 'previousSourceIds', 'settingsProvided') if k in context},
                    'sources': [{k: s.get(k) for k in ('id', 'title', 'location')} for s in context['library']],
                    'tools': catalogue, 'state': state(), 'hostRequirements': sorted(evaluator.required),
                    'limits': {'remainingRounds': self.max_rounds-rounds, 'remainingReplans': self.max_replans-replans}}, signal)
                check_cancel(signal)
                await self.tools.current()
                action = decision['action']
                if plan is None:
                    require('plan' in decision and action['type'] != 'revise_plan', 'AGENT_INITIAL_PLAN_REQUIRED')
                    plan = validate_plan(decision['plan'])
                    revisions.append(clone(plan))
                    yield event('plan', '学习计划：'+' → '.join(s['title'] for s in plan['steps']), 'completed')
                else:
                    require('plan' not in decision, 'AGENT_PLAN_CHANGE_REQUIRES_REVISION')
                decisions.append({k: clone(action[k]) for k in ('type', 'stepId', 'tool') if k in action} | {'round': rounds})
                if action['type'] == 'revise_plan':
                    require(replans < self.max_replans, 'AGENT_REPLAN_LIMIT')
                    plan = validate_plan(action['plan'], plan, completed)
                    revisions.append(clone(plan))
                    replans += 1
                    yield event('replan', '已根据执行结果调整后续步骤', 'completed')
                    continue
                if action['type'] == 'ask_user':
                    require(not re.search(r'密钥|密码|api[ _-]?key|token|令牌', action['question'], re.I), 'AGENT_INVALID_QUESTION')
                    yield event('clarify', '需要补充学习条件或实际作答', 'completed')
                    yield await terminal('awaiting_user', 'USER_INPUT_REQUIRED', question=action['question'])
                    return
                step_id = action['stepId']
                require(step_id in {s['id'] for s in plan['steps']}, 'AGENT_UNKNOWN_STEP')
                if action['type'] == 'finish':
                    missing, pending = evaluator.missing(plan, completed, step_id)
                    if action['completion'] == 'completed' and (missing or pending):
                        observations.append({'stepId': step_id, 'status': 'rejected', 'kind': 'completion-check',
                            'data': {'missingRequirements': missing, 'pendingSteps': pending}})
                        no_progress += 1
                        yield event('evaluate', '完成条件尚未满足，正在选择补充步骤', 'degraded')
                    else:
                        if action['completion'] == 'completed':
                            completed.add(step_id)
                        yield event('validate', '已核对本轮工具结果与来源', 'completed')
                        yield await terminal(action['completion'], 'FINISHED' if action['completion'] == 'completed' else 'INSUFFICIENT_RESULTS', action.get('answer'))
                        return
                else:
                    yield event('tool', TOOL_LABELS.get(action['tool'], '正在核对工具权限'))
                    try:
                        result = await self.tools.call(action['tool'], action['arguments'])
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        code = getattr(error, 'code', 'TOOL_FAILED')
                        if code in FATAL_CODES or not hasattr(error, 'code'):
                            raise
                        result = {'status': 'failed', 'data': {'error': code}, 'newInformation': False}
                    observations.append({'stepId': step_id, 'tool': action['tool'], 'arguments': clone(action['arguments']), **result})
                    if result['status'] == 'completed':
                        completed.add(step_id)
                    no_progress = 0 if result['newInformation'] else no_progress+1
                    yield event('observe', '已检查查询结果，正在决定下一步', 'completed' if result['status'] == 'completed' else 'degraded')
                if no_progress >= self.max_no_progress:
                    yield await terminal('awaiting_user', 'AGENT_NO_PROGRESS', question='连续查询未获得新的有效信息。请补充具体知识点、相关资料或你的解题过程。')
                    return
            yield await terminal('partial', 'AGENT_ROUND_LIMIT')
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = getattr(error, 'code', 'AGENT_EXECUTION_FAILED')
            if code == 'STALE_EVIDENCE':
                # Never publish facts gathered from a now-invalid snapshot.
                yield {'type': 'done', 'ok': True, 'answer': '资料已更新或移除，请重新选择有效资料后再提问。',
                    'sources': [], 'knowledgePoints': [], 'model': 'local-learning-tools', 'engine': 'local-workflow',
                    'agent': state('partial', code)}
                return
            yield event('evaluate', '本轮自动执行已停止，保留已核验结果', 'degraded')
            yield await terminal('partial', code)
