"""MiMo API transport, streaming cancellation and durable invocation accounting."""
from __future__ import annotations
import asyncio
import json
import re
from contextlib import asynccontextmanager
from uuid import uuid4
import httpx
from .common import AppError, digest, dumps, require, utc_now
from .rag_api import api_permit_held


class MimoProvider:
    def __init__(self, config, platform=None, transport=None):
        self.config, self.platform, self.transport = config, platform, transport

    @asynccontextmanager
    async def invocation(self, messages, scope):
        require(bool(self.config.api_key), "AI_UNAVAILABLE")
        request_id, release, state = None, None, {"usage": None, "complete": False}
        if self.platform:
            release = (lambda: None) if api_permit_held(self.platform) else self.platform.resources.acquire("api")
            require(release is not None, "API_BUSY")
            request_id = str(uuid4())
            try:
                self.platform.db.execute("INSERT INTO invocations(id,user_id,course_id,status,provider,request_hash,at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (request_id, scope.user_id, scope.course_id, "pending", "mimo", digest(messages), utc_now(), utc_now()))
            except BaseException:
                release()
                raise
        try:
            yield state
        finally:
            if request_id:
                try:
                    status = "succeeded" if state["complete"] else "unknown"
                    self.platform.db.execute("UPDATE invocations SET status=?,updated_at=?,usage_json=?,billing_status=? WHERE id=?", (status, utc_now(), dumps(state["usage"]) if state["usage"] else None, "unknown" if status == "unknown" else "not_reported", request_id))
                finally:
                    release()

    def client(self, timeout):
        return httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=self.transport, headers={"Authorization": "Bearer "+self.config.api_key, "Content-Type": "application/json"})

    async def generate(self, messages, *, scope=None, temperature=.2, timeout=25):
        async with self.invocation(messages, scope) as state:
            async with asyncio.timeout(timeout):
                async with self.client(timeout) as client:
                    async with client.stream("POST", self.config.base_url.rstrip("/")+"/chat/completions", json={"model": self.config.model, "temperature": temperature, "messages": messages}) as response:
                        require(response.is_success, "AI_UNAVAILABLE")
                        buffer = bytearray()
                        async for part in response.aiter_bytes():
                            buffer.extend(part)
                            require(len(buffer) <= 2097152, "AI_INVALID_RESPONSE")
                        data = json.loads(buffer)
                        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
                        require(isinstance(content, str), "AI_INVALID_RESPONSE")
                        state.update(complete=True, usage=data.get("usage"))
                        return {"content": content, "model": self.config.model, "usage": state["usage"]}

    async def stream(self, messages, *, scope=None, timeout=60):
        async with self.invocation(messages, scope) as state:
            async with asyncio.timeout(timeout):
                async with self.client(timeout) as client:
                    async with client.stream("POST", self.config.base_url.rstrip("/")+"/chat/completions", json={"model": self.config.model, "temperature": .2, "messages": messages, "stream": True}) as response:
                        require(response.is_success, "AI_UNAVAILABLE")
                        buffer, data_lines, size = "", [], 0

                        def events(frame):
                            if frame == "[DONE]":
                                return []
                            try:
                                payload = json.loads(frame)
                            except ValueError:
                                return []
                            if payload.get("usage"):
                                state["usage"] = payload["usage"]
                            delta = (payload.get("choices") or [{}])[0].get("delta", {})
                            return [{"type": kind, "text": delta[key], "model": self.config.model} for key, kind in (("reasoning_content", "reasoning"), ("content", "content")) if isinstance(delta.get(key), str) and delta[key]]

                        async for chunk in response.aiter_text():
                            size += len(chunk)
                            require(size <= 2097152, "AI_INVALID_RESPONSE")
                            buffer += chunk
                            # SSE permits CRLF, bare CR and multiple data: lines.
                            buffer = buffer.replace("\r\n", "\n")
                            buffer = re.sub(r"\r(?!$)", "\n", buffer)
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.rstrip("\r")
                                if not line:
                                    frame = "\n".join(data_lines)
                                    data_lines.clear()
                                    if frame == "[DONE]":
                                        state["complete"] = True
                                        return
                                    for event in events(frame):
                                        yield event
                                elif line.startswith("data:"):
                                    data_lines.append(line[5:].removeprefix(" "))
                        if buffer.startswith("data:"):
                            data_lines.append(buffer[5:].removeprefix(" "))
                        for event in events("\n".join(data_lines)) if data_lines else []:
                            yield event
                        state["complete"] = True
