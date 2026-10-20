"""Host-controlled learning interactions; model decisions never submit user answers."""
from backend.core import require, clone
from backend.agent.assessment import validate_question, public_quiz


class AgentInteractions:
    def __init__(self, host):
        self.host = host

    async def inputs(self, run):
        course = run['courseId']
        sources = await self.host.sources({'courseId': course,
            'selection': {'sourceIds': [s['id'] for s in run['context']['library']]}})
        study = self.host.scope_study_context(await self.host.study_context(course), sources)
        questions = []
        for question in study['questions']:
            try:
                questions.append(validate_question(question, sources))
            except (ValueError, KeyError, TypeError):
                continue
        return {**study, 'sources': sources, 'questions': questions,
            'examDate': run['context']['examDate'], 'minutes': run['context']['minutes'],
            **run.get('studySettings', {})}

    @staticmethod
    def ready(draft, title, **extra):
        return {'status': 'awaiting_confirmation', 'pendingDraft': draft,
            'interaction': {'kind': 'confirmation', 'title': title, 'digest': draft['digest'],
                'artifactKind': draft['kind'], 'preview': public_quiz(draft['content']) if draft['kind'] == 'quiz' else clone(draft['content']), **extra}}

    async def prepare(self, run):
        if run['scenario'] == 'exam':
            return await self.exam(run)
        if run['scenario'] == 'wrong' and not run.get('diagnosisConfirmed'):
            value = await self.inputs(run)
            valid = {s['id']: s['version'] for s in value['sources']}
            attempts = [a for a in self.host.repo.all(run['courseId']) if a.get('kind') == 'attempt']
            candidates = [(a, e) for a in attempts for e in a['content']['events']
                if e['grade']['status'] == 'graded' and e['grade']['score'] < e['grade']['maxScore']
                and valid.get(e['sourceId']) == e['sourceVersion']]
            if candidates:
                attempt, event = max(candidates, key=lambda pair: (pair[1]['createdAt'], pair[1]['id']))
                return {'status': 'awaiting_user', 'diagnosisTarget': {'attemptId': attempt['id'],
                    'eventId': event['id'], 'expectedRevision': attempt['revision']},
                    'interaction': {'kind': 'diagnosis', 'title': '请核对这道错题的实际原因',
                        'questionId': event['questionId'], 'answer': event['answer'], 'reasoning': event.get('reasoning', ''),
                        'causes': ['knowledge-gap', 'misread', 'calculation', 'method', 'notation', 'input-error', 'uncertain'],
                        'limitation': '错因由你确认，系统不从一次错误猜测真实思考过程。'}}
        return await self.practice(run)

    async def practice(self, run):
        value = await self.inputs(run)
        service = self.host.service(run['courseId'])
        session = await service.study_session({**value, 'practiceCount': 3})
        questions = [item['question'] for item in session['practice']['items']]
        if not questions:
            return {'status': 'awaiting_user', 'interaction': {'kind': 'missing_questions',
                'title': '当前章节没有可用的已审核练习，请先在题库补充或审核题目，再继续。',
                'diagnosis': session['estimates'], 'explanation': (run.get('result') or {}).get('answer', '')}}
        key = run['id']+'-quiz-'+str(run.get('cycle', 0))
        draft = await service.preview_quiz({'courseId': run['courseId'], 'id': key,
            'questions': questions, 'sources': value['sources'], 'count': min(3, len(questions))})
        return self.ready(draft, '核对本轮练习，确认后开始作答', diagnosis=session['estimates'], diagnosticActions=session['diagnosticActions'],
            explanation=(run.get('result') or {}).get('answer', ''), warnings=session['warnings'])

    async def review(self, run, attempt):
        events = attempt['content']['events']
        if any(e['grade']['status'] == 'awaiting_review' for e in events):
            return {'status': 'awaiting_user', 'attemptId': attempt['id'],
                'interaction': {'kind': 'awaiting_review', 'title': '主观题等待人工评分，评分完成后更新结果。'}}
        value = await self.inputs(run)
        service = self.host.service(run['courseId'])
        session = await service.study_session({**value, 'practiceCount': 3})
        key = run['id']+'-review-'+str(run.get('cycle', 0))
        draft = await service.preview_plan({**value, 'id': key})
        return {**self.ready(draft, '根据真实作答生成后续安排，确认后保存',
            grades=[{'questionId': e['questionId'], 'grade': e['grade']} for e in events],
            diagnosis=session['estimates'], nextPracticeIds=[i['question']['id'] for i in session['practice']['items']],
            limitation='本次作答仅用于调整安排，不代表已经完全掌握。'), 'attemptId': attempt['id']}

    async def exam(self, run):
        value = await self.inputs(run)
        if not value['graph']['concepts']:
            return {'status': 'awaiting_user', 'interaction': {'kind': 'missing_graph',
                'title': '请先在知识图谱中整理并核对当前资料的知识点，再生成跨章节安排。'}}
        service = self.host.service(run['courseId'])
        key = run.get('planId', run['id']+'-exam-plan')
        previous = await self.host.repo.get(run['courseId'], key)
        value.update(id=key, expectedRevision=previous['revision'] if previous else 0)
        draft = await (service.preview_replan(value) if previous else service.preview_plan(value))
        return {**self.ready(draft, '核对跨章节备考安排，确认后保存',
            changes={'previous': draft.get('previous'), 'proposed': draft['content']},
            basis={'gradedEvents': sum(e['grade']['status'] == 'graded' for e in value['events']),
                'conceptCount': len(value['graph']['concepts']), 'minutes': value['minutes'], 'examDate': value['examDate']}),
            'planId': key}

    async def act(self, run, action, body):
        service, course = self.host.service(run['courseId']), run['courseId']
        if action == 'diagnose':
            require(run.get('interaction', {}).get('kind') == 'diagnosis' and body.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            await service.diagnosis.correct({'courseId': course, **run['diagnosisTarget'],
                'cause': body.get('cause'), 'reason': body.get('reason'), 'confirmedBy': self.host.p.user_id,
                'operationId': run['id']+':diagnosis:'+str(run['revision'])})
            return {**await self.practice({**run, 'diagnosisConfirmed': True}), 'diagnosisConfirmed': True}
        if action == 'replan':
            require(run['scenario'] == 'exam', 'INVALID_SCENARIO')
            settings = body.get('settings', {})
            require(isinstance(settings, dict) and not set(settings)-{'examDate', 'minutes', 'availability'}, 'INVALID_PLAN')
            settings = {**run.get('studySettings', {}), **settings}
            return {**await self.exam({**run, 'studySettings': settings}), 'studySettings': settings}
        if action == 'confirm':
            require(run['status'] == 'awaiting_confirmation' and body.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            draft = run.get('pendingDraft')
            require(draft and body.get('digest') == draft['digest'], 'DRAFT_CHANGED')
            await self.host.validate_draft(course, draft)
            adopted = await service.artifacts.adopt(draft, {'confirmed': True, 'operationId': run['id']+':'+draft['digest']})
            if draft['kind'] == 'quiz':
                return {'status': 'awaiting_user', 'pendingDraft': None, 'quizId': adopted['id'], 'quizRevision': adopted['revision'],
                    'interaction': {'kind': 'quiz', 'title': '请提交你的实际答案', 'quiz': public_quiz(adopted['content'])}}
            return {'status': 'completed', 'pendingDraft': None, 'interaction': {'kind': 'completed',
                'title': '已保存后续学习安排', 'artifactId': adopted['id']}}
        if action == 'answer':
            require(run['status'] == 'awaiting_user' and run.get('interaction', {}).get('kind') == 'quiz', 'USER_ANSWER_NOT_EXPECTED')
            responses = body.get('responses')
            ids = {q['id'] for q in run['interaction']['quiz']['questions']}
            require(isinstance(responses, list) and len(responses) == len(ids) and
                all(isinstance(r, dict) and r.get('answer') is not None for r in responses) and
                {r.get('questionId') for r in responses} == ids, 'COMPLETE_USER_ANSWERS_REQUIRED')
            attempt = await service.submit_quiz({'courseId': course, 'id': run['id']+'-attempt-'+str(run.get('cycle', 0)),
                'quizId': run['quizId'], 'quizRevision': run['quizRevision'], 'responses': responses})
            return await self.review(run, attempt)
        if action == 'refresh':
            if run.get('attemptId'):
                attempt = await service._load(course, run['attemptId'], 'attempt')
                return await self.review(run, attempt)
            return await self.prepare(run)
        require(False, 'INVALID_ACTION')
