"""HTTP API router for Learning Space (Plan, Framework, Quiz, Today)."""
from __future__ import annotations

import re
import secrets
from contextlib import asynccontextmanager
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .common import require
from .study_space_service import StudySpaceService


def install_study_space(app):
    from .app import json_body, success
    router = APIRouter(prefix="/api/learning/space")
    previous=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(host):
        async with previous(host):
            from .space_planning import ConversationPlanning
            from .space_quiz import SpaceQuiz
            host.state.conversation_planning=ConversationPlanning(host)
            host.state.space_quiz=SpaceQuiz(host)
            yield
    app.router.lifespan_context=lifespan

    def authorize(request: Request):
        require(bool(re.fullmatch(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?", request.headers.get("host", ""))),
                "ORIGIN_FORBIDDEN")
        supplied = request.headers.get("origin")
        require(not supplied or supplied == str(request.base_url).rstrip("/"), "ORIGIN_FORBIDDEN")
        require(secrets.compare_digest(request.headers.get("x-xueya-token", ""), app.state.token), "AUTH_REQUIRED")

    def account_id(request: Request) -> str:
        account = getattr(app.state, "account", None)
        if account is not None and account.record():
            require(account.authorized(request), "AUTH_REQUIRED")
            record = account.current(request)
            return (record or {}).get('learningOwner') or (record or {}).get("username") or "local"
        return "local"

    def service() -> StudySpaceService:
        srv = getattr(app.state, "study_space", None)
        if srv is None:
            srv = StudySpaceService(app.state.platform)
            app.state.study_space = srv
        return srv

    # --- Today's Tasks & Continue Learning ---
    @router.post('/chat/plan')
    async def chat_plan(request: Request):
        authorize(request)
        value=await json_body(request,524288)
        return success(**app.state.conversation_planning.intake(account_id(request),value))

    @router.get('/jobs/{job_id}')
    async def plan_job(request: Request, job_id: str):
        authorize(request)
        job=app.state.platform.jobs.get(job_id,service()._scope(account_id(request)).user_id)
        require(job is not None,'JOB_NOT_FOUND')
        return success(job=job)

    @router.post('/jobs/{job_id}/cancel')
    async def cancel_plan_job(request: Request,job_id: str):
        authorize(request)
        job=app.state.platform.jobs.get(job_id,service()._scope(account_id(request)).user_id)
        require(job is not None,'JOB_NOT_FOUND')
        return success(job=app.state.platform.jobs.cancel(job['id'],service()._scope(account_id(request)).user_id))

    @router.get("/today")
    async def get_today(request: Request):
        authorize(request)
        return success(**service().get_today_summary(account_id(request)))

    # --- Study Plan Endpoints ---
    @router.get("/plan/active")
    async def get_active_plan(request: Request):
        authorize(request)
        plan = service().get_active_plan(account_id(request))
        return success(plan=plan)

    @router.get("/plan/list")
    async def list_plans(request: Request):
        authorize(request)
        return success(**service().list_plans(account_id(request)),jobs=app.state.conversation_planning.listing(account_id(request)))

    @router.post('/plan/generate')
    async def generate_plan_job(request: Request):
        authorize(request)
        data=await json_body(request,16384)
        return success(job=app.state.conversation_planning.submit(account_id(request),data))

    @router.get("/plan/{plan_id}")
    async def get_plan(request: Request, plan_id: str):
        authorize(request)
        plan = service().get_plan(account_id(request), plan_id)
        require(plan is not None, "PLAN_NOT_FOUND")
        return success(plan=plan)

    @router.post("/plan/draft")
    async def create_draft(request: Request):
        authorize(request)
        data = await json_body(request, 65536)
        plan = await service().generate_model_plan(account_id(request), app.state.provider, data)
        return success(plan=plan)

    @router.post("/plan/adopt")
    async def adopt_plan(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        plan_id = data.get("planId")
        expected_revision = data.get("expectedRevision", 1)
        require(type(expected_revision) is int, "INVALID_REVISION")
        confirmed = data.get("confirmed")
        plan = service().adopt_plan(account_id(request), plan_id, expected_revision, confirmed, data.get('operationId'))
        return success(plan=plan)

    @router.post('/plan/adjust-preview')
    async def adjust_plan(request: Request):
        authorize(request)
        data=await json_body(request,16384)
        return success(plan=service().adjust_plan_draft(account_id(request),data))

    @router.post('/plan/task/link')
    async def link_task(request: Request):
        authorize(request)
        data=await json_body(request,16384)
        return success(**service().attach_task_link(account_id(request),data))

    @router.post("/plan/task/toggle")
    async def toggle_task(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        plan_id = data.get("planId")
        task_id = data.get("taskId")
        completed = data.get("completed")
        res = service().toggle_task(account_id(request), plan_id, task_id, completed,
                                    expected_revision=data.get('expectedRevision'),operation_id=data.get('operationId'))
        return success(**res)

    @router.post("/plan/task/delay")
    async def delay_task(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        plan_id = data.get("planId")
        task_id = data.get("taskId")
        new_date = data.get("newDate")
        res = service().delay_task(account_id(request), plan_id, task_id, new_date,
                                   expected_revision=data.get('expectedRevision'),operation_id=data.get('operationId'))
        return success(**res)

    @router.post("/plan/sync-course")
    async def sync_course(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        course_id = data.get("courseId")
        episode_id = data.get("episodeId")
        completed = data.get("completed")
        count = service().sync_course_completion(account_id(request), course_id, episode_id, completed)
        return success(syncedTasks=count)

    # --- Knowledge Framework Endpoints ---
    @router.post("/framework/generate")
    async def generate_framework(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        subject = data.get("subject", "数据结构")
        topic = data.get("topic", "")
        fw = await service().generate_model_framework(account_id(request), app.state.provider, subject, topic)
        return success(framework=fw)

    @router.get("/framework/list")
    async def list_frameworks(request: Request):
        authorize(request)
        fws = service().list_frameworks(account_id(request))
        return success(frameworks=fws)

    @router.get("/framework/{framework_id}")
    async def get_framework(request: Request, framework_id: str):
        authorize(request)
        fw = service().get_framework(account_id(request), framework_id)
        require(fw is not None, "FRAMEWORK_NOT_FOUND")
        return success(framework=fw)

    @router.post("/framework/{framework_id}/patch")
    async def patch_framework(request: Request, framework_id: str):
        authorize(request)
        patch = await json_body(request, 65536)
        fw = service().patch_framework(account_id(request), framework_id, patch)
        return success(framework=fw)

    @router.delete("/framework/{framework_id}")
    async def delete_framework(request: Request, framework_id: str):
        authorize(request)
        ok = service().delete_framework(account_id(request), framework_id)
        return success(deleted=ok)

    # --- Interactive Chat Quiz Endpoints ---
    @router.post('/chat/quiz')
    async def chat_quiz(request: Request):
        authorize(request)
        data=await json_body(request,65536)
        return success(**app.state.space_quiz.chat(account_id(request),data))
    @router.get('/quiz/list')
    async def quiz_list(request: Request):
        authorize(request)
        return success(**app.state.space_quiz.listing(account_id(request)))

    @router.post('/quiz/jobs')
    async def quiz_generation_job(request: Request):
        authorize(request)
        data=await json_body(request,16384)
        return success(job=app.state.space_quiz.submit_generation(account_id(request),data))

    @router.get('/quiz/question/{question_id}')
    async def quiz_question(request: Request,question_id: str):
        authorize(request)
        question=app.state.space_quiz.question(account_id(request),question_id)
        return success(question={**service().public_question(question),'revision':question['revision']})

    @router.post('/quiz/attempts')
    async def quiz_attempt(request: Request):
        authorize(request)
        data=await json_body(request,32768)
        return success(attempt=app.state.space_quiz.submit_attempt(account_id(request),data))

    @router.get('/quiz/attempts/{attempt_id}')
    async def quiz_attempt_read(request: Request,attempt_id: str):
        authorize(request)
        return success(attempt=app.state.space_quiz.public_attempt(app.state.space_quiz.attempt(account_id(request),attempt_id)))

    @router.post('/quiz/attempts/{attempt_id}/{action}')
    async def quiz_review(request: Request,attempt_id: str,action: str):
        authorize(request)
        require(action in ('review','correct'),'NOT_FOUND')
        data=await json_body(request,16384)
        return success(attempt=app.state.space_quiz.review(account_id(request),attempt_id,data,manual=action=='correct'))

    @router.post("/quiz/generate")
    async def generate_quiz(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        subject = data.get("subject", "数据结构")
        q_type = data.get("type", "single")
        raw_q = await service().generate_model_question(account_id(request), app.state.provider, subject, q_type)
        # Store internal question with answer
        scope = service()._scope(account_id(request))
        service().repo.put(scope, "question", raw_q["id"], raw_q, expected_version=0)
        # Public question hides correct answer and rubrics
        return success(question=service().public_question(raw_q))

    @router.post("/quiz/grade")
    async def grade_quiz(request: Request):
        authorize(request)
        data = await json_body(request, 32768)
        question_id = data.get("questionId")
        user_answer = data.get("answer")
        scope = service()._scope(account_id(request))
        row = service().repo.read(scope, "question", question_id)
        require(row is not None, "QUESTION_NOT_FOUND")
        raw_q = row["value"]
        attempt=app.state.space_quiz.submit_attempt(account_id(request),{'questionId':question_id,'questionRevision':row['version'],
            'answer':user_answer,'operationId':data.get('operationId') or 'legacy-'+secrets.token_hex(16)})
        result=attempt.get('effectiveEvaluation',{}).get('result') or {'status':'queued','jobId':attempt['evaluations'][-1].get('jobId')}
        return success(result=result,attempt=attempt)

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app
