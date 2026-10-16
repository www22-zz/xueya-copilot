"""Shared JSON, validation and error semantics, including Node snapshot compatibility."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AppError(code)


def dumps(value: Any, *, canonical: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=canonical, allow_nan=False)


def digest(value: Any, *, canonical: bool = False) -> str:
    # ensure_ascii=False matches JSON.stringify for persisted content hashes.
    return hashlib.sha256(dumps(value, canonical=canonical).encode()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def identifier(value: Any) -> str:
    require(isinstance(value, str) and 0 < len(value) <= 150 and bool(re.fullmatch(r"[\w.:-]+", value)), "INVALID_ID")
    return value


class Scope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
    user_id: str = Field(alias="userId")
    course_id: str = Field(alias="courseId")

    @model_validator(mode="after")
    def check_ids(self):
        identifier(self.user_id)
        identifier(self.course_id)
        return self

    def wire(self) -> dict:
        return self.model_dump(by_alias=True)


KINDS = frozenset("document source note question attempt event concept plan review session run checkpoint artifact vector".split())


def validate_workspace(value: Any) -> dict:
    require(isinstance(value, dict) and value.get("version") == 3, "INVALID_WORKSPACE")
    courses = value.get("courses")
    require(isinstance(courses, list) and 1 <= len(courses) <= 100, "INVALID_WORKSPACE")
    seen = set()
    for course in courses:
        require(isinstance(course, dict), "INVALID_WORKSPACE")
        course_id = identifier(course.get("id"))
        require(course_id not in seen, "DUPLICATE_COURSE")
        seen.add(course_id)
        require(isinstance(course.get("name"), str) and 0 < len(course["name"]) <= 100, "INVALID_COURSE")
        require(isinstance(course.get("data"), dict), "INVALID_WORKSPACE")
        for key in ("documents", "cards", "bank", "records", "messages", "sessions", "plan", "reviewLog"):
            require(isinstance(course["data"].get(key, []), list), "INVALID_WORKSPACE")
    require(any(c["id"] == value.get("activeId") and not c.get("archived") for c in courses), "ACTIVE_COURSE_REQUIRED")
    return value
