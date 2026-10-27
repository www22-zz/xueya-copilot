"""Completion is derived from executed tools, never the model's claim of success."""
from ..core import dumps
import re
from .answer_policy import finalize_answer
from .tasks import answer_unavailable, study_text


class ResultEvaluator:
    def __init__(self, request, context, tools, intent, review=None):
        self.request, self.context, self.tools, self.intent = request, context, tools, intent
        self.review = review
        self.required = {'progress', 'review_plan'} if intent == 'plan' else {'progress'} if intent == 'review' else {'evidence'}
        if re.search(r'错题', request['question']):
            self.required |= {'progress', 'wrong_questions'}

    def missing(self, plan, completed, finishing_step):
        results = self.tools.results
        available = set()
        if self.tools.evidence:
            available.add('evidence')
        for name, key in [('analyze_progress', 'progress'), ('list_wrong_questions', 'wrong_questions'),
                          ('get_review_queue', 'review_queue'), ('get_course_graph', 'graph')]:
            if name in results:
                available.add(key)
        if results.get('build_review_plan', {}).get('days'):
            available.add('review_plan')
        requirements = self.required | set(plan['requirements'])
        pending = {s['id'] for s in plan['steps']} - set(completed) - {finishing_step}
        return sorted(requirements-available), sorted(pending)

    async def render(self, answer=None):
        results, sources, parts, artifacts = self.tools.results, list(self.tools.evidence.values()), [], {}
        used_ids = [s['id'] for s in sources]
        verification, model, engine = 'tool-results-only', 'local-learning-tools', 'local-workflow'
        unavailable = {}
        if 'analyze_progress' in results:
            stats, plan = results['analyze_progress'], results.get('build_review_plan')
            artifacts['progress'] = stats
            if plan is not None:
                artifacts['plan'] = plan
            parts.append(study_text('plan' if plan else 'review', stats, plan, self.context['baseDate']))
        if sources:
            if answer and isinstance(answer.get('answer'), str) and isinstance(answer.get('sources'), list):
                try:
                    value = await finalize_answer(dumps(answer), sources, 'external-planner', question=self.request['question'], mode=self.request['mode'], review=self.review)
                    parts.append(value['answer'])
                    used_ids = value['sources']
                    verification, model, engine = value['verification'], value['model'], value['engine']
                    if value.get('answerStatus'):
                        unavailable = {k: value[k] for k in ('answerStatus', 'reason') if k in value}
                except (ValueError, TypeError, KeyError, AttributeError):
                    parts.append(answer_unavailable('AI_INVALID_RESPONSE'))
                    verification = 'not-generated'
                    unavailable = {'answerStatus': 'unavailable', 'reason': 'AI_INVALID_RESPONSE'}
            elif self.intent not in ('plan', 'review'):
                parts.append(answer_unavailable('AI_ANSWER_MISSING'))
                verification = 'not-generated'
                unavailable = {'answerStatus': 'unavailable', 'reason': 'AI_ANSWER_MISSING'}
        if 'list_wrong_questions' in results:
            parts.append(f"本次读取到 {len(results['list_wrong_questions']['items'])} 道历史错题；真实错因仍需结合解题过程核对。")
        if 'get_review_queue' in results:
            parts.append(f"当前到期复习卡：{len(results['get_review_queue']['cards'])} 张。尚未代你完成复习或评分。")
        if 'get_course_graph' in results:
            graph = results['get_course_graph'].get('content', results['get_course_graph'])
            parts.append(f"已读取课程图谱：{len(graph['concepts'])} 个概念、{len(graph['edges'])} 条关系。")
        return {'ok': True, 'answer': '\n\n'.join(parts) or '当前还没有足够的已核验工具结果，请补充学习目标或相关课程资料。',
                'sources': used_ids, 'knowledgePoints': [], 'model': model, 'engine': engine,
                'verification': verification, 'artifacts': artifacts, **unavailable}
