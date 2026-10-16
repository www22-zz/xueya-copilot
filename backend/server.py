"""Run from the project root: python -m backend.server."""
import uvicorn
import json
import os
import secrets
import uuid
from fastapi import Request
from fastapi.responses import JSONResponse
from .app import create_app
from .config import load_config


def main():
    config = load_config()
    directory = config['platform']['dataDir']
    directory.mkdir(parents=True, exist_ok=True)
    pid_file = directory/'server.json'
    if pid_file.exists():
        old = json.loads(pid_file.read_text(encoding='utf-8'))
        try:
            os.kill(old['pid'], 0)
        except ProcessLookupError:
            pid_file.unlink()
        else:
            raise RuntimeError('ANOTHER_PLATFORM_INSTANCE_RUNNING')
    identity = {'pid': os.getpid(), 'port': config['port'], 'instanceId': str(uuid.uuid4()), 'stopToken': secrets.token_hex(32)}
    with pid_file.open('x', encoding='utf-8') as stream:
        json.dump(identity, stream)
    app = None
    try:
        app = create_app(config)
        app.state.instance_id = identity['instanceId']
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=config['port'], log_level='info'))
        # This private host route is not advertised as an MCP tool.
        @app.middleware('http')
        async def shutdown(request: Request, call_next):
            if request.url.path == '/api/platform/shutdown' and request.method == 'POST' and secrets.compare_digest(request.headers.get('x-xueya-stop', ''), identity['stopToken']):
                server.should_exit = True
                return JSONResponse({'ok': True})
            return await call_next(request)
        server.run()
    finally:
        if pid_file.exists() and json.loads(pid_file.read_text(encoding='utf-8')).get('instanceId') == identity['instanceId']:
            pid_file.unlink()


if __name__ == '__main__':
    main()
