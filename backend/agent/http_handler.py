"""Optional authenticated learning API, mounted only with E's real ports."""
import re
import uuid
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from ..core import require, clone, resolve, DomainError
from ..contracts import LIMITS

POST_PATHS = {'answers', 'questions/generate', 'quiz/preview', 'attempts', 'attempts/review', 'diagnosis/analyze', 'diagnosis/correct', 'plan/preview', 'plan/change', 'note/edit', 'card/preview', 'reviews/rate', 'reviews/queue', 'draft/adopt', 'chapter', 'runs/resume', 'runs/cancel', 'study/session', 'package/preview', 'package/plan', 'plan/replan', 'recommendation/feedback', 'reviews/defer'}


def http_status(code):
    for pattern, status in [('NOT_FOUND', 404), ('CONFLICT|STALE|CHANGED|NOT_RESUMABLE|OUTCOME', 409), ('SCOPE|COURSE_MISMATCH', 403), ('CONFIGURED|REQUIRED_REPOSITORY|UNAVAILABLE|BUDGET|QUEUE_NOT', 503)]:
        if re.search(pattern, code):
            return status
    return 400


def identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[\w:.-]{1,160}', value))


class LearningHandler:
    def __init__(self, learning, resolve_context, resolve_evidence, resolve_questions, preview_store, enqueue=None, validate_draft=None):
        require(learning and callable(resolve_context) and callable(resolve_evidence) and callable(resolve_questions) and hasattr(preview_store, 'put') and hasattr(preview_store, 'get'), 'LEARNING_HTTP_PORTS_REQUIRED')
        self.learning, self.resolve_context, self.resolve_evidence, self.resolve_questions, self.previews, self.enqueue = learning, resolve_context, resolve_evidence, resolve_questions, preview_store, enqueue
        self.validate_draft = validate_draft
        self.router = APIRouter(prefix='/api/learning')
        self.router.add_api_route('/{path:path}', self.handle, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])

    async def _preview(self, course, draft):
        key = str(uuid.uuid4())
        await self.previews.put(course, key, clone(draft))
        return {'draftId': key, 'draft': draft}

    async def handle(self, path: str, request: Request):
        read = path not in POST_PATHS and request.method == 'GET' and path.startswith(('quiz/', 'runs/'))
        if path not in POST_PATHS and not read:
            return JSONResponse({'ok': False, 'error': 'ROUTE_NOT_FOUND'}, status_code=404)
        if not read and request.method != 'POST':
            return JSONResponse({'ok': False, 'error': 'METHOD_NOT_ALLOWED'}, status_code=405)
        try:
            raw = bytearray()
            if not read:
                async for chunk in request.stream():
                    raw.extend(chunk)
                    require(len(raw) <= LIMITS['requestBytes'], 'REQUEST_TOO_LARGE')
                import json
                try:
                    body = json.loads(raw)
                except ValueError:
                    raise DomainError('INVALID_JSON') from None
            else:
                body = {}
            require(isinstance(body, dict), 'INVALID_REQUEST')
            context = await resolve(self.resolve_context(request))
            course = context.get('courseId')
            require(isinstance(course, str) and course, 'COURSE_SCOPE_REQUIRED')
            require('courseId' not in body or body['courseId'] == course, 'COURSE_MISMATCH')
            result, status = await self.dispatch(path, body, context)
            return JSONResponse({'ok': True, 'result': result}, status_code=status)
        except DomainError as error:
            return JSONResponse({'ok': False, 'error': error.code}, status_code=413 if error.code == 'REQUEST_TOO_LARGE' else http_status(error.code))
        except (KeyError, TypeError, ValueError):
            return JSONResponse({'ok': False, 'error': 'LEARNING_REQUEST_FAILED'}, status_code=400)

    async def dispatch(self, path, body, context):
        learning, course = self.learning, context['courseId']
        def fields(*keys):
            return {k: body[k] for k in keys if k in body} | {'courseId': course}
        async def evidence():
            return await resolve(self.resolve_evidence({'courseId': course, 'selection': body.get('selection')}))
        async def actual():
            require(callable(context.get('loadStudyContext')), 'STUDY_CONTEXT_REQUIRED')
            return await resolve(context['loadStudyContext']())
        status = 200
        if path == 'answers':
            result = await learning.answers.answer({**fields('question', 'history'), 'sources': await evidence()})
        elif path == 'questions/generate':
            result = await learning.questions.generate({**fields('count', 'types', 'conceptIds'), 'sources': await evidence()})
        elif path == 'quiz/preview':
            require(identifier(body.get('id')) and isinstance(body.get('questionIds'), list) and all(identifier(x) for x in body['questionIds']), 'INVALID_QUIZ')
            questions = await resolve(self.resolve_questions({'courseId': course, 'ids': body['questionIds']}))
            result = await self._preview(course, await learning.preview_quiz({**fields('id', 'count', 'conceptIds', 'expectedRevision'), 'questions': questions, 'sources': await evidence()}))
        elif path in ('study/session', 'package/preview', 'plan/preview', 'plan/replan'):
            value = {**await actual(), **fields('id', 'expectedRevision', 'examDate', 'minutes', 'availability', 'practiceCount'), 'sources': await evidence()}
            if path == 'study/session':
                result = await learning.study_session(value)
            else:
                require(identifier(body.get('id')), 'INVALID_ARTIFACT')
                method = {'package/preview': learning.preview_learning_package, 'plan/preview': learning.preview_plan, 'plan/replan': learning.preview_replan}[path]
                result = await self._preview(course, await method(value))
        elif path == 'draft/adopt':
            require(identifier(body.get('draftId')) and identifier(body.get('operationId')) and body.get('confirmed') is True, 'CONFIRMATION_REQUIRED')
            require('draft' not in body and 'content' not in body, 'DRAFT_CHANGED')
            draft = await self.previews.get(course, body['draftId'])
            require(draft and draft['courseId'] == course, 'DRAFT_NOT_FOUND')
            # A receipt can be replayed even after its source is retired. A new
            # write must first verify that its server-held evidence is current.
            old = await learning.repository.get_operation(course, body['operationId'])
            if self.validate_draft and not old:
                await resolve(self.validate_draft(course, draft))
            result = await learning.artifacts.adopt(draft, {'confirmed': True, 'operationId': body['operationId']})
        elif path == 'chapter':
            require(self.enqueue, 'QUEUE_NOT_CONFIGURED')
            require(identifier(body.get('id')) and identifier(body.get('artifactId')), 'INVALID_RUN')
            study = await actual() if context.get('loadStudyContext') else {}
            result = await learning.start_chapter({**study, **fields('id', 'artifactId', 'expectedRevision'), 'sources': await evidence()})
            await resolve(self.enqueue({'courseId': course, 'runId': result['id']}))
            status = 202
        elif path == 'runs/resume':
            require(self.enqueue and learning.workflow, 'QUEUE_NOT_CONFIGURED')
            result = await learning.workflow.resume(course, body['id'], {k: body[k] for k in ('revision', 'confirmation', 'acknowledgeUnknown', 'userInput') if k in body})
            await resolve(self.enqueue({'courseId': course, 'runId': result['id']}))
            status = 202
        elif path == 'runs/cancel':
            require(learning.workflow, 'RUN_REPOSITORY_REQUIRED')
            result = await learning.workflow.cancel(course, body['id'])
        elif path.startswith('quiz/') and path not in POST_PATHS:
            result = await learning.get_quiz(course, path[5:])
        elif path.startswith('runs/') and path not in POST_PATHS:
            require(learning.workflow, 'RUN_REPOSITORY_REQUIRED')
            result = await learning.workflow.get(course, path[5:])
        else:
            routes = {
                'attempts': (learning.submit_quiz, ('quizId', 'quizRevision', 'id', 'responses'), False),
                'attempts/review': (learning.correct_subjective, ('attemptId', 'expectedRevision', 'questionId', 'review', 'operationId'), False),
                'diagnosis/analyze': (learning.diagnosis.analyze, ('attemptId',), False),
                'diagnosis/correct': (learning.diagnosis.correct, ('attemptId', 'eventId', 'expectedRevision', 'operationId', 'cause', 'reason'), False),
                'package/plan': (learning.preview_package_plan, ('packageId', 'id', 'expectedRevision'), True),
                'plan/change': (learning.preview_plan_change, ('id', 'expectedRevision', 'change'), True),
                'note/edit': (learning.preview_note_edit, ('id', 'expectedRevision', 'text'), True),
                'card/preview': (learning.reviews.preview, ('id', 'prompt', 'answer', 'evidence', 'expectedRevision'), True),
                'reviews/rate': (learning.reviews.rate, ('id', 'rating', 'expectedRevision', 'operationId'), False),
                'reviews/queue': (learning.reviews.queue, ('cardIds',), False),
                'reviews/defer': (learning.reviews.defer, ('id', 'expectedRevision', 'operationId', 'until', 'reason'), False),
                'recommendation/feedback': (learning.feedback.record, ('itemId', 'action', 'until', 'reason', 'operationId', 'expectedRevision'), False)}
            require(path in routes, 'ROUTE_NOT_FOUND')
            method, keys, preview = routes[path]
            value = fields(*keys)
            if path == 'diagnosis/correct':
                value['confirmedBy'] = context.get('userId', 'local-learner')
            if path == 'card/preview':
                value['sources'] = await evidence()
            result = await method(value)
            if preview:
                result = await self._preview(course, result)
        return result, status
