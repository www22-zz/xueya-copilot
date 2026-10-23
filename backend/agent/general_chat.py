from datetime import date
from contextlib import aclosing
import json
from ..core import require, parse_model_json, check_cancel, today


async def general_chat(model, request, signal=None, *, plain_text=False):
    current = today()
    calendar = f"服务器当前日期（Asia/Shanghai）：{current}，星期{'一二三四五六日'[date.fromisoformat(current).weekday()]}。这只提供日期，不提供天气、新闻等实时信息。"
    output = '直接输出回答正文，不要为了接口格式包装成 JSON。' if plain_text else '只输出 JSON {"answer":"回答正文"}。'
    messages = [{'role': 'system', 'content': '你是学涯 Copilot，友好的中文助手，回答日常问题、一般知识和学习疑问。本次为通用问答，没有可引用的课程原文，不得声称已查看用户资料或编造页码、实时信息和工具结果。不确定时明确说明。历史仅供理解语境。'+output+calendar}, *request['history'], {'role': 'user', 'content': request['question']}]
    content, name, size, announced = '', None, 0, False
    parameters = {'messages': messages, 'signal': signal, **({} if plain_text else {'responseFormat': {'type': 'json_object'}})}
    if callable(getattr(model, 'stream', None)):
        async with aclosing(model.stream(parameters)) as events:
            async for event in events:
                check_cancel(signal)
                name = event.get('model', name)
                if event.get('type') in ('content', 'reasoning') and isinstance(event.get('text'), str):
                    size += len(event['text'])
                    require(size <= 200000, 'AI_INVALID_RESPONSE')
                    if event['type'] == 'content':
                        content += event['text']
                        if plain_text:
                            # The host owns wire JSON; arbitrary model prose/code is data.
                            fragment = ('{"answer":"' if not announced else '')+json.dumps(event['text'], ensure_ascii=False)[1:-1]
                            announced = True
                            yield {**event, 'text': fragment}
                            continue
                    yield event
    else:
        result = await model.generate(parameters)
        content, name = result['content'], result.get('model')
    check_cancel(signal)
    if plain_text:
        require(isinstance(content, str) and content.strip(), 'AI_EMPTY')
        answer = content.strip()
        if announced:
            yield {'type': 'content', 'text': '"}', 'model': name}
    else:
        parsed = parse_model_json(content)
        require(isinstance(parsed, dict) and isinstance(parsed.get('answer'), str) and parsed['answer'].strip(), 'AI_INVALID_RESPONSE')
        answer = parsed['answer'].strip()
    yield {'type': 'done', 'ok': True, 'answer': answer[:16000], 'sources': [], 'knowledgePoints': [], 'model': name, 'engine': 'general-chat', 'verification': 'general-knowledge-not-course-verified'}
