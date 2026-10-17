"""Learning facade; durable stores, scope and queue remain integration ports."""
from ..core import require, clone, fingerprint, now_iso, date_at
from .artifact_service import ArtifactService
from .content_service import ContentService
from .answer_service import AnswerService
from .question_service import QuestionService, select_practice
from .concept_service import ConceptService
from .review_service import ReviewService
from .diagnosis_service import DiagnosisService
from .recommendation_feedback import RecommendationFeedback
from .assessment import validate_question, assemble_quiz, public_quiz, attempt_event, review_subjective, diagnose
from .evidence import evidence_package
from .study import mastery
from .concepts import validate_graph
from .planning import plan_study, revise_plan, replan_study
from .study_session import build_study_session
from .run_service import RunService


class LearningService:
    def __init__(self, repository, *, runs=None, model=None, model_id=None, review=None, review_version=None, question_review=None, checkpoint=None, verify_snapshot=None, clock=now_iso):
        require(hasattr(repository, 'get_operation'), 'OPERATION_LOOKUP_REQUIRED')
        self.repository, self.runs, self.clock = repository, runs, clock
        self.artifacts = ArtifactService(repository, clock)
        self.content = ContentService(model, model_id, review, review_version, checkpoint)
        self.answers, self.questions, self.concepts = AnswerService(model, review), QuestionService(model, question_review, clock), ConceptService(model)
        self.reviews, self.feedback, self.diagnosis = ReviewService(repository, clock), RecommendationFeedback(repository, clock), DiagnosisService(repository, clock)
        self.workflow = RunService(runs, {'chapter': self._chapter, 'preview': self._preview, 'adopt': self._adopt}, verify_snapshot) if runs else None
        self.model = model

    async def _study_input(self, value):
        state = await self.feedback.get(value['courseId'])
        cards = value.get('cards')
        if cards is None:
            cards = (await self.reviews.catalog({'courseId': value['courseId'], 'cardIds': value['cardIds']}))['cards'] if 'cardIds' in value else []
        return {**value, 'baseDate': value.get('baseDate', date_at(self.clock())), 'now': value.get('now', self.clock()), 'cards': cards, 'feedback': state['content']['events'], 'feedbackRevision': state['revision']}

    async def study_session(self, value):
        return build_study_session(await self._study_input(value))

    async def _load(self, course, key, kind):
        row = await self.repository.get(course, key)
        require(row and row['courseId'] == course and row['kind'] == kind, 'ARTIFACT_NOT_FOUND')
        return row

    async def preview_quiz(self, value):
        validated = [validate_question(q, value['sources']) for q in value['questions']]
        quiz = assemble_quiz(validated, value)
        require(quiz['questions'], 'NO_APPROVED_QUESTIONS')
        return await self.artifacts.preview({**value, 'kind': 'quiz', 'content': quiz})

    async def _load_quiz(self, course, key):
        row = await self.repository.get(course, key)
        require(row and row['courseId'] == course and row['kind'] in ('quiz', 'learning-package'), 'ARTIFACT_NOT_FOUND')
        quiz = row['content'] if row['kind'] == 'quiz' else row['content']['quiz']
        require(quiz.get('questions'), 'NO_APPROVED_QUESTIONS')
        return {**row, 'content': quiz}

    async def get_quiz(self, course, key):
        return public_quiz((await self._load_quiz(course, key))['content'])

    async def submit_quiz(self, value):
        require(isinstance(value.get('id'), str) and value['id'].strip() and len(value['id']) <= 160 and value.get('quizId') and type(value.get('quizRevision')) is int and value['quizRevision'] >= 1 and isinstance(value.get('responses'), list), 'INVALID_SUBMISSION')
        course, key, operation = value['courseId'], value['id'], 'submit:'+value['id']
        digest = fingerprint({k: value[k] for k in ('quizId', 'quizRevision', 'responses')})
        old = await self.repository.get_operation(course, operation)
        if old:
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return old['value']
        quiz = await self._load_quiz(course, value['quizId'])
        require(quiz['revision'] == value['quizRevision'], 'QUIZ_VERSION_CONFLICT')
        responses = value['responses']
        ids = [r.get('questionId') for r in responses]
        require(len(set(ids)) == len(ids) and all(key in [q['id'] for q in quiz['content']['questions']] for key in ids), 'INVALID_SUBMISSION')
        created = value.get('createdAt', self.clock())
        events = []
        for q in quiz['content']['questions']:
            response = next((r for r in responses if r['questionId'] == q['id']), {})
            events.append(attempt_event(q, {**response, 'id': fingerprint([key, q['id']]), 'createdAt': created}))
        content = {'quizId': value['quizId'], 'quizRevision': value['quizRevision'], 'events': events, 'questionSnapshots': clone(quiz['content']['questions']), 'diagnoses': [{'eventId': e['id'], **diagnose(e)} for e in events]}
        return await self.repository.commit({'courseId': course, 'id': key, 'operationId': operation, 'requestHash': digest, 'expectedRevision': 0, 'value': {'courseId': course, 'id': key, 'kind': 'attempt', 'revision': 1, 'content': content, 'updatedAt': created}})

    async def correct_subjective(self, value):
        require(value.get('operationId'), 'IDEMPOTENCY_KEY_REQUIRED')
        digest = fingerprint({k: value[k] for k in ('attemptId', 'expectedRevision', 'questionId', 'review')})
        course = value['courseId']
        old = await self.repository.get_operation(course, value['operationId'])
        if old:
            require(old['requestHash'] == digest, 'IDEMPOTENCY_CONFLICT')
            return old['value']
        row = await self._load(course, value['attemptId'], 'attempt')
        require(row['revision'] == value['expectedRevision'], 'ARTIFACT_CONFLICT')
        q = next((q for q in row['content'].get('questionSnapshots', []) if q['id'] == value['questionId']), None)
        require(q, 'QUESTION_NOT_FOUND')
        grade = review_subjective(q, value['review'])
        content = clone(row['content'])
        for event in content['events']:
            if event['questionId'] == q['id']:
                event.update(grade=grade, reviewedAt=self.clock())
        content['diagnoses'] = [{'eventId': e['id'], **diagnose(e)} if e['questionId'] == q['id'] else next((d for d in content['diagnoses'] if d['eventId'] == e['id']), {'eventId': e['id'], **diagnose(e)}) for e in content['events']]
        return await self.repository.commit({'courseId': course, 'id': row['id'], 'operationId': value['operationId'], 'requestHash': digest, 'expectedRevision': row['revision'], 'value': {**row, 'revision': row['revision']+1, 'updatedAt': self.clock(), 'content': content}})

    async def preview_plan(self, value):
        graph = validate_graph(value['graph'], value['sources'])
        hydrated = await self._study_input(value)
        estimates = mastery(value['events'], {'courseId': value['courseId'], 'baseDate': hydrated['baseDate']})
        content = plan_study({**hydrated, 'graph': graph, 'estimates': estimates})
        content['evidenceVersion'] = evidence_package(value)['version']
        return await self.artifacts.preview({**value, 'kind': 'plan', 'content': content})

    async def preview_plan_change(self, value):
        row = await self._load(value['courseId'], value['id'], 'plan')
        require(row['revision'] == value['expectedRevision'], 'ARTIFACT_CONFLICT')
        return await self.artifacts.preview({**value, 'kind': 'plan', 'content': revise_plan(row['content'], value['change'])})

    async def preview_replan(self, value):
        row = await self._load(value['courseId'], value['id'], 'plan')
        require(row['revision'] == value['expectedRevision'], 'ARTIFACT_CONFLICT')
        hydrated = await self._study_input(value)
        graph = validate_graph(value['graph'], value['sources'])
        estimates = mastery(value.get('events', []), {'courseId': value['courseId'], 'baseDate': hydrated['baseDate']})
        content = replan_study(row['content'], {**hydrated, 'graph': graph, 'estimates': estimates})
        content['evidenceVersion'] = evidence_package(value)['version']
        return await self.artifacts.preview({**value, 'kind': 'plan', 'content': content})

    async def preview_learning_package(self, value, **options):
        content = await self.content.learning_package(await self._study_input(value), **options)
        return await self.artifacts.preview({**value, 'kind': 'learning-package', 'content': content})

    async def preview_package_plan(self, value):
        row = await self._load(value['courseId'], value['packageId'], 'learning-package')
        require(row['content'].get('plan'), 'PACKAGE_PLAN_NOT_FOUND')
        content = {**clone(row['content']['plan']), 'sourcePackage': {'id': value['packageId'], 'revision': row['revision']}}
        return await self.artifacts.preview({**value, 'kind': 'plan', 'content': content})

    async def preview_note_edit(self, value):
        text = value.get('text')
        require(isinstance(text, str) and text.strip() and len(text) <= 120000, 'INVALID_NOTE')
        row = await self.repository.get(value['courseId'], value['id'])
        require(row and row['courseId'] == value['courseId'] and row['kind'] in ('note', 'knowledge-card'), 'ARTIFACT_NOT_FOUND')
        return await self.artifacts.preview({**value, 'kind': row['kind'], 'content': {**clone(row['content']), 'text': text, 'editedBy': 'user'}})

    async def _chapter(self, step):
        return await self.content.learning_package(step['input'], signal=step['signal'])

    async def _preview(self, step):
        result = next((s['output'] for s in step['previous'] if s['type'] == 'chapter'), None)
        require(result, 'MISSING_CHAPTER_RESULT')
        return await self.artifacts.preview({'courseId': step['courseId'], 'id': step['input']['artifactId'], 'kind': 'learning-package', 'content': result, 'runId': step['runId'], 'expectedRevision': step['input'].get('expectedRevision', 0)})

    async def _adopt(self, step):
        draft = next((s['output'] for s in step['previous'] if s['type'] == 'preview'), None)
        require(draft, 'MISSING_PREVIEW')
        return await self.artifacts.adopt(draft, {'confirmed': True, 'operationId': step['idempotencyKey']})

    async def start_chapter(self, value):
        require(self.workflow, 'RUN_REPOSITORY_REQUIRED')
        require(value.get('artifactId'), 'ARTIFACT_ID_REQUIRED')
        old = await self.runs.get(value['courseId'], value['id'])
        input_value = {k: v for k, v in value.items() if k != 'id'}
        if old:
            for k in ('now', 'baseDate'):
                if k not in input_value:
                    input_value[k] = old['input'][k]
        hydrated = await self._study_input(input_value)
        pack = evidence_package(hydrated)
        return await self.workflow.create({'courseId': value['courseId'], 'id': value['id'], 'input': hydrated, 'snapshot': pack['version'], 'steps': [
            {'id': 'chapter', 'type': 'chapter', 'effect': 'remote' if self.model else 'read'}, {'id': 'preview', 'type': 'preview', 'effect': 'read'}, {'id': 'adopt', 'type': 'adopt', 'effect': 'write'}]})
