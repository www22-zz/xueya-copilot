"""Optional shared local-space login; no new store or change to data ownership."""
import asyncio
import hashlib
import json
import re
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .common import require

KEY = 'local-account-v1'
COOKIE = 'xueya_session'
TTL = 8*60*60
ITERATIONS = 600_000


class LocalAccount:
    def __init__(self, platform):
        self.platform = platform
        self.sessions = {}
        self.lock = asyncio.Lock()
        self.failures = 0
        self.blocked_until = 0

    def record(self):
        row = self.platform.db.one('SELECT value FROM meta WHERE key=?', (KEY,))
        return json.loads(row['value']) if row else None

    def authorized(self, request):
        if not self.record():
            return True
        token = request.cookies.get(COOKIE, '')
        if not token or len(token) > 256:
            return False
        key = hashlib.sha256(token.encode()).hexdigest()
        expiry = self.sessions.get(key, 0)
        if expiry <= time.monotonic():
            self.sessions.pop(key, None)
            return False
        return True

    @staticmethod
    def derive(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()

    def issue(self, username):
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if v > now}
        token = secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = now+TTL
        response = JSONResponse({'ok': True, 'username': username})
        response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite='strict', path='/')
        response.headers['Cache-Control'] = 'no-store'
        return response


def install_account(app):
    from .app import json_body, error_response
    router = APIRouter()

    def origin(request):
        require(bool(re.fullmatch(r'(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?', request.headers.get('host', ''))), 'ORIGIN_FORBIDDEN')
        supplied = request.headers.get('origin')
        require(not supplied or supplied == str(request.base_url).rstrip('/'), 'ORIGIN_FORBIDDEN')

    def token(request):
        origin(request)
        require(secrets.compare_digest(request.headers.get('x-xueya-token', ''), app.state.token), 'AUTH_REQUIRED')

    def password(value):
        text = value.get('password')
        require(isinstance(text, str) and 6 <= len(text) <= 256, 'PASSWORD_LENGTH')
        return text

    @router.get('/api/account/status')
    async def status(request: Request):
        origin(request)
        account = app.state.account
        row = account.record()
        return JSONResponse({'ok': True, 'configured': bool(row), 'authenticated': account.authorized(request),
                             'username': row['username'] if row else None, 'sharedSpace': True}, headers={'Cache-Control': 'no-store'})

    @router.post('/api/account/setup')
    async def setup(request: Request):
        token(request)
        value = await json_body(request, 4096)
        username = value.get('username')
        require(isinstance(username, str) and bool(re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username)), 'INVALID_USERNAME')
        secret = password(value)
        account = app.state.account
        async with account.lock:
            require(not account.record(), 'ACCOUNT_ALREADY_CONFIGURED')
            salt = secrets.token_hex(16)
            derived = await asyncio.to_thread(account.derive, secret, salt)
            account.platform.db.execute('INSERT INTO meta(key,value) VALUES(?,?)', (KEY, json.dumps({'username': username, 'salt': salt, 'hash': derived, 'iterations': ITERATIONS})))
            return account.issue(username)

    @router.post('/api/account/login')
    async def login(request: Request):
        origin(request)
        value = await json_body(request, 4096)
        account = app.state.account
        async with account.lock:
            if time.monotonic() < account.blocked_until:
                return error_response('LOGIN_THROTTLED', 429)
            row = account.record()
            require(row is not None, 'ACCOUNT_NOT_CONFIGURED')
            supplied = value.get('password')
            if not isinstance(supplied, str) or len(supplied) > 256:
                supplied = ''
            hashed = await asyncio.to_thread(account.derive, supplied, row['salt'])
            if not secrets.compare_digest(hashed, row['hash']) or value.get('username') != row['username']:
                account.failures += 1
                if account.failures >= 5:
                    account.blocked_until = time.monotonic()+60
                    account.failures = 0
                return error_response('LOGIN_INVALID', 401)
            account.failures = 0
            return account.issue(row['username'])

    @router.post('/api/account/logout')
    async def logout(request: Request):
        token(request)
        account = app.state.account
        raw = request.cookies.get(COOKIE, '')
        account.sessions.pop(hashlib.sha256(raw.encode()).hexdigest(), None)
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE, path='/')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @router.post('/api/account/password')
    async def change_password(request: Request):
        token(request)
        value = await json_body(request, 4096)
        secret = password(value)
        account = app.state.account
        async with account.lock:
            row = account.record()
            require(row is not None, 'ACCOUNT_NOT_CONFIGURED')
            current = value.get('currentPassword')
            require(isinstance(current, str) and len(current) <= 256, 'LOGIN_INVALID')
            derived = await asyncio.to_thread(account.derive, current, row['salt'])
            require(secrets.compare_digest(derived, row['hash']), 'LOGIN_INVALID')
            if 'username' in value:
                username = value['username']
                require(isinstance(username, str) and bool(re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username)), 'INVALID_USERNAME')
                row['username'] = username
            row['salt'] = secrets.token_hex(16)
            row['hash'] = await asyncio.to_thread(account.derive, secret, row['salt'])
            account.platform.db.execute('UPDATE meta SET value=? WHERE key=?', (json.dumps(row), KEY))
            account.sessions.clear()
            return account.issue(row['username'])

    before = len(app.router.routes)
    app.include_router(router)
    added = app.router.routes[before:]
    del app.router.routes[before:]
    app.router.routes[0:0] = added
