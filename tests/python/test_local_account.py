import json
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config


def test_optional_account_protects_every_api_and_preserves_shared_data(tmp_path):
    config=Config(data_dir=tmp_path/'data')
    app=create_app(config)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert not client.get('/api/account/status').json()['configured']
        token=client.get('/api/platform/bootstrap').json()['token']
        headers={'X-Xueya-Token':token}
        body={'username':'xueya-team','password':'controlled-shared-password'}
        assert client.post('/api/account/setup',json=body).status_code==403
        setup=client.post('/api/account/setup',json=body,headers=headers)
        assert setup.status_code==200
        assert 'HttpOnly' in setup.headers['set-cookie'] and 'SameSite=strict' in setup.headers['set-cookie']
        raw=app.state.platform.db.one("SELECT value FROM meta WHERE key='local-account-v1'")['value']
        record=json.loads(raw)
        assert body['password'] not in raw and record['iterations']==600000
        assert client.get('/api/platform/bootstrap').status_code==200
        assert len(app.state.platform.repo.courses(app.state.platform.user_id))==1
        cookie=client.cookies.get('xueya_session')
        assert client.post('/api/account/logout',json={},headers=headers).status_code==200
        for path in ['/api/platform/bootstrap','/api/learning/workspace','/api/platform/documents']:
            assert client.get(path,headers=headers).status_code==401
        assert client.post('/api/parse',content=b'private',headers=headers).status_code==401
        assert client.get('/api/platform/bootstrap',headers={'Cookie':'xueya_session='+cookie}).status_code==401
        assert client.get('/api/health').status_code==200
        assert client.post('/api/account/login',json={**body,'password':'bad'}).status_code==401
        assert client.post('/api/account/login',json=body,headers={'Origin':'https://evil.invalid'}).status_code==403
        assert client.post('/api/account/login',json=body).status_code==200
        old=client.cookies.get('xueya_session')
        new='123456'
        assert client.post('/api/account/password',json={'currentPassword':'bad','password':new},headers=headers).status_code!=200
        assert client.post('/api/account/password',json={'currentPassword':body['password'],'password':new,'username':'123456'},headers=headers).status_code==200
        assert client.get('/api/platform/bootstrap',headers={'Cookie':'xueya_session='+old}).status_code==401
        assert len(app.state.platform.repo.courses(app.state.platform.user_id))==1
    app=create_app(config)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/platform/bootstrap').status_code==401
        assert client.post('/api/account/login',json={'username':'123456','password':new}).status_code==200
        assert client.get('/api/platform/bootstrap').status_code==200


def test_login_throttle_and_setup_race_guard(client):
    headers=client.platform_headers
    body={'username':'shared-team','password':'controlled-team-password'}
    assert client.post('/api/account/setup',json={**body,'password':'short'},headers=headers).status_code==400
    assert client.post('/api/account/setup',json=body,headers=headers).status_code==200
    assert client.post('/api/account/setup',json=body,headers=headers).status_code!=200
    client.cookies.clear()
    for _ in range(5):
        assert client.post('/api/account/login',json={**body,'password':'bad'}).status_code==401
    assert client.post('/api/account/login',json=body).status_code==429
