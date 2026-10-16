"""Host-controlled generic tool gateway. Remote annotations never grant permissions."""
from __future__ import annotations
import asyncio
import copy
import re
import time
from jsonschema import Draft202012Validator
from .common import AppError, dumps, require
from .mcp_core import Limiter


class ToolGateway:
    def __init__(self, *, timeout=10, duration=60, max_calls=64, max_cost_units=64, max_concurrent=4, allowed_tools=None, on_trace=None):
        self.tools, self.timeout, self.deadline = {}, timeout, time.monotonic()+duration
        self.max_calls, self.max_cost_units, self.calls, self.cost = max_calls, max_cost_units, 0, 0
        self.limiter, self.allowed = Limiter(max_concurrent), set(allowed_tools) if allowed_tools is not None else None
        self.on_trace, self.pending = on_trace, set()

    def register(self, definition, handler):
        metadata = copy.deepcopy(definition)
        name = metadata.get("name")
        require(isinstance(name, str) and bool(re.fullmatch(r"[-a-zA-Z0-9_]{1,150}", name)) and callable(handler), "INVALID_TOOL")
        require(name not in self.tools, "DUPLICATE_TOOL")
        schema = metadata.setdefault("inputSchema", {"type": "object"})
        Draft202012Validator.check_schema(schema)
        cost = metadata.pop("costUnits", 1)
        require(type(cost) is int and 1 <= cost <= 64, "INVALID_TOOL")
        metadata["_meta"] = {"version": metadata.pop("version", "1.0.0"), "risk": metadata.pop("risk", "unknown")}
        self.tools[name] = (metadata, handler, Draft202012Validator(schema), cost)

    async def register_server(self, server_id, adapter, *, risks=None):
        require(bool(re.fullmatch(r"[a-zA-Z0-9_-]+", server_id)), "INVALID_MCP_ADAPTER")
        definitions = await adapter.list_tools()
        require(isinstance(definitions, list), "INVALID_MCP_ADAPTER")
        # Build and validate in isolation so failed discovery cannot partially register tools.
        staging = ToolGateway()
        for definition in definitions:
            original = definition.get("name")
            require(isinstance(original, str), "INVALID_MCP_ADAPTER")
            name = server_id+"__"+original
            require(name not in self.tools, "DUPLICATE_TOOL")

            async def call(args, original=original):
                return await adapter.call_tool(original, args)
            staging.register({**definition, "name": name, "risk": (risks or {}).get(original, "unknown")}, call)
        self.tools.update(staging.tools)

    async def list_tools(self):
        return [copy.deepcopy(metadata) for name, (metadata, _, _, _) in self.tools.items() if self.allowed is None or name in self.allowed]

    async def call_tool(self, name, args=None):
        require(name in self.tools, "TOOL_NOT_FOUND")
        require(self.allowed is None or name in self.allowed, "TOOL_FORBIDDEN")
        metadata, handler, validator, cost = self.tools[name]
        args = {} if args is None else args
        require(isinstance(args, dict) and validator.is_valid(args), "INVALID_TOOL_ARGUMENTS")
        require(len(dumps(args).encode()) <= 65536, "TOOL_ARGUMENTS_TOO_LARGE")
        require(time.monotonic() < self.deadline and self.calls < self.max_calls and self.cost+cost <= self.max_cost_units, "TOOL_BUDGET_EXCEEDED")
        release, started, status = self.limiter.acquire(), time.monotonic(), "completed"
        self.calls += 1
        self.cost += cost

        async def execute():
            try:
                return await handler(copy.deepcopy(args))
            finally:
                release()
        task = asyncio.create_task(execute())
        self.pending.add(task)

        def finished(t):
            self.pending.discard(t)
            if not t.cancelled():
                t.exception()  # timed-out tasks must not emit unhandled exception warnings
        task.add_done_callback(finished)
        try:
            done, _ = await asyncio.wait([task], timeout=min(self.timeout, max(.001, self.deadline-time.monotonic())))
            if not done:
                task.cancel()
                raise AppError("TOOL_TIMEOUT")
            result = task.result()
            require(isinstance(result, dict) and isinstance(result.get("content"), list) and len(result["content"]) <= 16 and all(isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str) for block in result["content"]), "INVALID_TOOL_RESULT")
            require(len(dumps(result).encode()) <= 131072, "TOOL_RESULT_TOO_LARGE")
            return result
        except BaseException as error:
            status = error.code if isinstance(error, AppError) else "TOOL_ABORTED" if isinstance(error, asyncio.CancelledError) else "TOOL_FAILED"
            if not task.done():
                task.cancel()
            raise
        finally:
            if self.on_trace:
                try:
                    self.on_trace({"tool": name, "status": status, "durationMs": round((time.monotonic()-started)*1000), "calls": self.calls, "costUnits": self.cost})
                except Exception:
                    pass
