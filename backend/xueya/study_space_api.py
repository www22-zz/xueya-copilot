"""HTTP API router for Learning Space (Plan, Framework, Quiz, Today)."""
from __future__ import annotations

import re
import secrets
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .common import require
from .study_space_service import StudySpaceService


def install_study_space(app):
    from .app import json_body, success
    router = APIRouter(prefix="/api/learning/space")

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
            return (record or {}).get("username") or "local"
        return "local"

    def service() -> StudySpaceService:
        srv = getattr(app.state, "study_space", None)
        if srv is None:
            srv = StudySpaceService(app.state.platform)
            app.state.study_space = srv
        return srv

    # --- Today's Tasks & Continue Learning ---
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
        return success(**service().list_plans(account_id(request)))

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
        plan = service().adopt_plan(account_id(request), plan_id, expected_revision, confirmed)
        return success(plan=plan)

    @router.post("/plan/task/toggle")
    async def toggle_task(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        plan_id = data.get("planId")
        task_id = data.get("taskId")
        completed = data.get("completed")
        res = service().toggle_task(account_id(request), plan_id, task_id, completed)
        return success(**res)

    @router.post("/plan/task/delay")
    async def delay_task(request: Request):
        authorize(request)
        data = await json_body(request, 16384)
        plan_id = data.get("planId")
        task_id = data.get("taskId")
        new_date = data.get("newDate")
        res = service().delay_task(account_id(request), plan_id, task_id, new_date)
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
        result = await service().evaluate_model_answer(account_id(request), app.state.provider, raw_q, user_answer) if raw_q["type"] == "short" else service().grade_submission(raw_q, user_answer)
        attempt_id = "attempt-" + secrets.token_hex(12)
        service().repo.put(scope, "attempt", attempt_id, {"id": attempt_id, "questionId":question_id,"questionSnapshot":raw_q,"answer":user_answer,"evaluation":result}, expected_version=0)

        return success(result=result)

    count = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[count:]
    del app.router.routes[count:]
    app.router.routes[0:0] = added
    return app
