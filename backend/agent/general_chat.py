from ..core import require, parse_model_json, check_cancel


async def general_chat(model, request, signal=None):
    messages = [{'role': 'system', 'content': '你是学涯 Copilot，友好的中文助手，回答日常问题、一般知识和学习疑问。本次为通用问答，没有可引用的课程原文，不得声称已查看用户资料或编造页码、实时信息和工具结果。不确定时明确说明。历史仅供理解语境。只输出 JSON {"answer":"回答正文"}。'}, *request['history'], {'role': 'user', 'content': request['question']}]
    content, name, size = '', None, 0
    parameters = {'messages': messages, 'signal': signal, 'responseFormat': {'type': 'json_object'}}
    if callable(getattr(model, 'stream', None)):
        async for event in model.stream(parameters):
            check_cancel(signal)
            name = event.get('model', name)
            if event.get('type') in ('content', 'reasoning') and isinstance(event.get('text'), str):
                size += len(event['text'])
                require(size <= 200000, 'AI_INVALID_RESPONSE')
                if event['type'] == 'content':
                    content += event['text']
                yield event
    else:
        result = await model.generate(parameters)
        content, name = result['content'], result.get('model')
    check_cancel(signal)
    parsed = parse_model_json(content)
    require(isinstance(parsed, dict) and isinstance(parsed.get('answer'), str) and parsed['answer'].strip(), 'AI_INVALID_RESPONSE')
    yield {'type': 'done', 'ok': True, 'answer': parsed['answer'].strip()[:16000], 'sources': [], 'knowledgePoints': [], 'model': name, 'engine': 'general-chat', 'verification': 'general-knowledge-not-course-verified'}
