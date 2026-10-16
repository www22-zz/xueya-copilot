"""Local-only Uvicorn host, single-instance identity and authenticated graceful stop."""
import asyncio
import json
import os
import secrets
import socket
from uuid import uuid4
import uvicorn
from .app import create_app
from .common import AppError, dumps, require
from .config import load_config


def pid_alive(pid):
    require(type(pid) is int and pid > 0, "INVALID_SERVER_PID")
    if os.name == "nt":
        # os.kill(pid, 0) is CTRL_C_EVENT on Windows; it is NOT a safe liveness probe.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # fail closed except an absent PID
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


async def serve():
    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    lock = config.data_dir / "server.json"
    if lock.exists():
        old = json.loads(lock.read_text(encoding="utf-8"))
        if not pid_alive(old["pid"]):
            lock.unlink()
        else:
            raise AppError("ANOTHER_PLATFORM_INSTANCE_RUNNING")
    identity = {"pid": os.getpid(), "port": config.port, "instanceId": str(uuid4()), "stopToken": secrets.token_hex(32)}
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(dumps(identity))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", config.port))
        sock.listen(2048)
        identity["port"] = sock.getsockname()[1]
        lock.write_text(dumps(identity), encoding="utf-8")
        app = create_app(config)
        app.state.instance_id, app.state.stop_token = identity["instanceId"], identity["stopToken"]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=identity["port"], log_level="warning", access_log=False, timeout_graceful_shutdown=5))
        app.state.request_stop = lambda: setattr(server, "should_exit", True)
        print("Xueya Copilot (Python) running at http://127.0.0.1:"+str(identity["port"]), flush=True)
        await server.serve(sockets=[sock])
        require(server.started, "SERVER_START_FAILED")
    finally:
        sock.close()
        if lock.exists() and json.loads(lock.read_text(encoding="utf-8")).get("instanceId") == identity["instanceId"]:
            lock.unlink()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        asyncio.run(serve())
    except AppError as error:
        print(error.code, file=__import__("sys").stderr)
        raise SystemExit(1)
