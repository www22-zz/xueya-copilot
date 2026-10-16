from __future__ import annotations
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import socket
import threading
import time
import pytest
import uvicorn
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.platform import Platform


@pytest.fixture
def workspace():
    return {"version": 3, "activeId": "course-default", "courses": [{"id": "course-default", "name": "数据结构", "archived": False, "data": {"documents": [], "cards": [], "bank": [], "records": [], "messages": [{"id": f"m{i}", "role": "user", "text": f"历史{i}"} for i in range(40)], "sessions": [], "plan": []}}]}


@pytest.fixture
def platform(tmp_path):
    p = Platform(tmp_path / "data")
    yield p
    asyncio.run(p.close())


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(data_dir=tmp_path / "http-data"))
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.platform = app.state.platform
        c.platform_headers = {"X-Xueya-Token": c.get("/api/platform/bootstrap").json()["token"]}
        yield c


@contextmanager
def live_server(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            assert thread.is_alive(), "server startup failed"
            time.sleep(.02)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
        assert not thread.is_alive(), "server failed to stop"
