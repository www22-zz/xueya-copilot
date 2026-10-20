"""Controlled planner replies for offline tests only; never a production model."""
import json
import httpx


def planner_response(payload):
    messages = payload.get('messages', [])
    if not messages or 'xueya.readonly-agent.v1' not in str(messages[0].get('content', '')):
        return None
    value = json.loads(messages[-1]['content'])
    state, needed = value['state'], value['hostRequirements']
    observations = state['observations']
    order = []
    if 'progress' in needed:
        order.append(('progress', 'analyze_progress', {}))
    if 'wrong_questions' in needed:
        order.append(('wrong', 'list_wrong_questions', {'limit': 10}))
    if 'review_plan' in needed:
        order.append(('schedule', 'build_review_plan', {}))
    if 'evidence' in needed:
        order.extend([('find', 'search_materials', {'query': value['request']['question'], 'limit': 6}),
                      ('read', 'read_source', {})])
    done = {o.get('stepId') for o in observations if o.get('status') == 'completed'}
    action = {'type': 'finish', 'stepId': 'answer', 'completion': 'completed'}
    for step, tool, args in order:
        if step in done:
            continue
        if tool == 'read_source':
            found = next((o['data'].get('sources', []) for o in observations if o.get('tool') == 'search_materials'), [])
            if not found:
                action = {'type': 'ask_user', 'question': '当前检索没有找到相关原文，请补充课程关键词或资料。'}
                break
            source = max(found, key=lambda s: len(s.get('excerpt', '')))
            args = {'sourceId': source['id']}
        action = {'type': 'call_tool', 'stepId': step, 'tool': tool, 'arguments': args}
        break
    else:
        source = next((o['data'].get('source') for o in observations if o.get('tool') == 'read_source'), None)
        if source:
            action['answer'] = {'answer': source['quote'], 'sources': [source['id']], 'knowledgePoints': []}
    decision = {'action': action}
    if state['plan'] is None:
        decision['plan'] = {'goal': '完成本轮只读学习准备', 'requirements': needed,
            'steps': [{'id': step, 'title': step} for step, _, _ in order]+[{'id': 'answer', 'title': '核对并整理结果'}]}
    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(decision, ensure_ascii=False)}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 50, 'completion_tokens': 100}})
