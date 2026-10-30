"""Explicit one-shot MiMo fallback, isolated from course evidence and citations."""
from contextlib import aclosing
import json
import logging
import httpx

from .common import dumps
from .qa_latency import current_timing

REASONS = frozenset({
    'NO_RELEVANT_KNOWLEDGE', 'INSUFFICIENT_EVIDENCE', 'CLAIMS_NEED_REVIEW',
    'AI_ANSWER_MISSING', 'AI_EMPTY', 'AI_TRUNCATED', 'AI_INCOMPLETE',
    'AI_INVALID_RESPONSE', 'AI_INVALID_RESPONSE_FORMAT', 'INVALID_CLAIM_EVIDENCE',
    'INVALID_CLAIMS', 'UNSUPPORTED_CLAIM', 'INVALID_CITATION',
    'AI_UNEXPECTED_TOOL_CALL', 'AI_GENERATION_FAILED', 'AI_TIMEOUT', 'AI_UNAVAILABLE',
})
PREFIX = '模型自主回答（未使用知识库证据）：\n\n'


def eligible(config, request, failure):
    if not getattr(config, 'rag_general_fallback', False) or not getattr(config, 'api_key', ''):
        return False
    if request.get('mode') != 'ask' or failure.get('answerStatus') != 'unavailable':
        return False
    if failure.get('engine') in ('general-chat', 'general-chat-unavailable', 'assistant-info', 'web-search-synthesized'):
        return False
    if failure.get('fallback') or failure.get('reason') not in REASONS:
        return False
    agent = failure.get('agent') or {}
    if agent.get('status') in ('awaiting_user', 'awaiting_confirmation'):
        return False
    return True


async def stream_general_fallback(agent, request, scope, failure):
    reason = failure['reason']
    steps = list((failure.get('workflow') or {}).get('steps', []))
    metadata = {'from': 'course-rag', 'reason': reason, 'attempts': 1, 'sameRequestReplayed': False}
    step = {'stage': 'general-fallback', 'status': 'running',
            'label': '知识库回答未满足要求，正在切换一次MiMo自主回答（不引用课程资料）'}
    steps.append(step)
    # Optional fields extend the existing workflow frame. The browser discards
    # an earlier partial JSON answer before displaying a different answer mode.
    yield {'type': 'workflow', **step, 'resetAnswer': True, 'fallback': metadata}
    timing = current_timing.get()
    if timing:
        timing.route = 'general-fallback'
    source_free = {key: request[key] for key in ('question', 'history', 'mode')}
    first = True
    fragments = []
    try:
        async with aclosing(agent.general(source_free, scope, fallback=True)) as events:
            async for event in events:
                if event['type'] == 'content':
                    text = event['text']
                    if first and text.startswith('{"answer":"'):
                        text = '{"answer":"'+dumps(PREFIX)[1:-1]+text[len('{"answer":"'):]
                        first = False
                    fragments.append(text)
                    yield {**event, 'text': text}
                elif event['type'] == 'done':
                    steps.append({'stage': 'general-fallback', 'status': 'completed', 'label': 'MiMo自主回答已完成，未使用知识库证据'})
                    yield {**event, 'answer': PREFIX+event['answer'], 'answerStatus': 'answered',
                           'engine': 'general-chat', 'sources': [], 'sourceObjects': [], 'sourceDetails': [],
                           'claims': [], 'fallback': metadata,
                           'verification': 'general-knowledge-not-course-verified',
                           'workflow': {'intent': 'general-fallback', 'steps': steps},
                           **({'toolCalls': failure['toolCalls']} if failure.get('toolCalls') else {}),
                           **({'agent': {'status': 'completed', 'planRevision': 0}} if failure.get('agent') else {})}
                else:
                    yield event
    except Exception as error:
        code = getattr(error, 'code', None) or ('AI_TIMEOUT' if isinstance(error, (TimeoutError, httpx.TimeoutException)) else 'AI_CONNECTION_FAILED' if isinstance(error, httpx.TransportError) else 'GENERAL_FALLBACK_FAILED')
        logging.getLogger(__name__).warning('general fallback failed: %s (%s)', code, type(error).__name__)
        # Preserve source-free prose already received on transport interruption.
        # Never promote it to a complete or course-verified answer.
        if code in ('AI_TIMEOUT', 'AI_INCOMPLETE', 'AI_TRUNCATED', 'AI_UNAVAILABLE', 'AI_CONNECTION_FAILED') and fragments:
            try:
                partial = json.loads(''.join(fragments) + '\"}')['answer']
            except (ValueError, KeyError, TypeError):
                partial = ''
            if partial.removeprefix(PREFIX).strip():
                yield {'type': 'content', 'text': '\"}'}
                steps.append({'stage': 'general-fallback', 'status': 'degraded', 'label': '自主回答中断，保留已生成内容'})
                yield {'type': 'done', 'ok': True, 'answer': partial + '\n\n（本次生成中断，以上内容尚未完成。）',
                       'sources': [], 'sourceObjects': [], 'sourceDetails': [], 'claims': [], 'knowledgePoints': [],
                       'engine': 'general-chat', 'model': getattr(agent.model.config, 'model', 'unconfigured'),
                       'answerStatus': 'unavailable', 'reason': code, 'partial': True,
                       'verification': 'general-knowledge-not-course-verified', 'fallback': metadata,
                       'workflow': {'intent': 'general-fallback', 'steps': steps}}
                return
        steps.append({'stage': 'general-fallback', 'status': 'degraded', 'label': 'MiMo自主回答也未完成，已停止自动调用'})
        yield {'type': 'workflow', **steps[-1], 'resetAnswer': True, 'fallback': metadata}
        yield {'type': 'done', 'ok': True, 'answer': '知识库回答未完成，MiMo自主回答也暂未完成。已停止自动调用，没有循环重试；请稍后手动重试。',
               'sources': [], 'sourceObjects': [], 'sourceDetails': [], 'claims': [], 'knowledgePoints': [],
               'engine': 'general-chat-unavailable', 'model': getattr(agent.model.config, 'model', 'unconfigured'),
               'answerStatus': 'unavailable', 'reason': code,
               'verification': 'not-generated', 'fallback': {**metadata, 'failureReason': code},
               'workflow': {'intent': 'general-fallback', 'steps': steps}}
