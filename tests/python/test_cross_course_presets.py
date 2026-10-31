"""Only the six explicitly approved identities can cross legacy public courses.

Real CPU parsing of the approved Markdown, not a forged fileHash or a mock RAG.
No migration/indexing of the developer's private library and no external API.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.xueya.account_scope import account_owner, bind_owner
from backend.xueya.app import create_app
from backend.xueya.common import AppError, Scope
from backend.xueya.config import Config
from backend.xueya.rag_scope_adapter import KNOWN_PLATFORM_HASHES, ScopeAdapter, public_api_value
from tests.python.test_private_library_boundary import login, upload
from tests.python.test_rag import completed

ROOT=Path(__file__).resolve().parents[2]
MATERIAL=ROOT/'materials/stack-queue/栈与队列知识库.md'


@pytest.fixture
def library(tmp_path,http_root):
    app=create_app(Config(root=http_root,data_dir=tmp_path/'data',preserve_legacy_data=True),start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        p,rag=app.state.platform,app.state.rag
        original=Scope(user_id=p.user_id,course_id='preset-stack-queue')
        p.repo.ensure_course(p.user_id,{'id':original.course_id,'name':'栈与队列公共教材'})
        job=rag.upload(original,MATERIAL.read_bytes(),MATERIAL.name,'approved-original')
        state=asyncio.run(completed(p,job));assert state['status']=='succeeded',state
        document=rag.document(original,state['result']['documentId'])
        # A named/flagged, but unlisted, document in that other course must not
        # become cross-course public merely because it says isPlatform/sample.
        job=rag.upload(original,b'UNLISTED_OTHER_COURSE_7263 stack notes','栈与队列知识库-额外.md','unlisted-other')
        state=asyncio.run(completed(p,job));assert state['status']=='succeeded'
        row=p.repo.read(original,'document',state['result']['documentId'])
        p.repo.put(original,'document',row['id'],{**row['value'],'isPlatform':True,'sample':True,
            'sourceFileHash':document['fileHash']},row['version'])
        alice=login(client,'alice',True)
        yield app,client,original,document,alice


def test_allowlist_is_exactly_the_approved_manifest_plus_markdown():
    manifest=json.loads((ROOT/'materials/data-structures-algorithms/manifest.json').read_text(encoding='utf-8'))
    approved={d['sha256'] for d in manifest['documents'][:5]}
    approved.add(hashlib.sha256(MATERIAL.read_bytes()).hexdigest())
    assert len(approved)==6 and KNOWN_PLATFORM_HASHES==approved


def test_two_accounts_search_and_read_public_metadata_at_actual_origin(library):
    app,client,original,document,alice=library
    p,rag=app.state.platform,app.state.rag
    private_job=upload(app,client,alice)
    owner=account_owner(app.state.account.find('alice')[0])
    adapter=ScopeAdapter(p,owner)
    sources=adapter.sources(rag,'course-default')
    public=next(s for s in sources if s.get('isPlatform'))
    assert public['scopeOrigin']=={'user_id':p.user_id,'course_id':original.course_id}
    assert public['originCourseId']==original.course_id and public['originCourseName']=='栈与队列公共教材'
    assert not any('UNLISTED_OTHER_COURSE_7263' in s['quote'] for s in sources)
    assert any('ALICE_PRIVATE_8137' in s['quote'] for s in sources)
    assert adapter.validate_citation(rag,public,'course-default')
    with bind_owner(owner):
        scope=p.scope()
        details=app.state.agent.source_details(scope,[public['id']])
        assert details[0]['courseId']=='course-default'
        assert details[0]['scopeOrigin']['course_id']==original.course_id
        assert adapter.validate_citation(rag,details[0],'course-default')
        snapshot=app.state.agent.evidence_snapshot(scope,[public])
        assert app.state.agent.evidence_current(scope,[public],snapshot)
    for headers in (alice,login(client,'bobby',True)):
        response=client.post('/api/platform/rag/search',headers=headers,json={
            'query':'循环队列 front rear','mode':'lexical','budget':3000,'limit':8})
        assert response.status_code==200,response.text
        evidence=response.json()['evidence'];assert evidence['sources']
        assert all(s['isPlatform'] and 'quote' not in s for s in evidence['sources'])
        assert all(s['originCourseId']==original.course_id for s in evidence['sources'])
        assert private_job['result']['documentId'] not in response.text
        read=client.get('/api/platform/rag/read?sourceId='+public['id'],headers=headers)
        assert read.status_code==200 and read.json()['protected'] and 'quote' not in read.json()['source']
        assert read.json()['source']['originCourseId']==original.course_id
        raw=adapter.resolve_source(public['id'],'course-default')[1]
        assert client.get('/api/platform/rag/read?sourceId='+raw,headers=headers).status_code>=400
        for kind in ('original','export'):
            assert client.get('/api/platform/rag/'+kind+'?documentId='+document['id'],headers=headers).status_code>=400
        tool=client.post('/api/platform/tools/call',headers=headers,json={'name':'read_source','arguments':{'sourceId':public['id']}})
        assert tool.status_code==200 and 'quote' not in tool.text
        assert original.course_id in tool.text
    # Request scopes do not alter either the origin or the legacy identity.
    assert p.user_id=='local-user' and rag.document(original,document['id'])['fileHash'] in KNOWN_PLATFORM_HASHES


def test_origin_forgery_and_cross_course_flag_only_source_are_denied(library):
    app,client,original,_,alice=library;p,rag=app.state.platform,app.state.rag
    owner=account_owner(app.state.account.find('alice')[0]);adapter=ScopeAdapter(p,owner)
    public=next(s for s in adapter.sources(rag,'course-default') if s.get('isPlatform'))
    wrong={**public,'scopeOrigin':{'user_id':p.user_id,'course_id':'course-default'}}
    with pytest.raises(AppError,match='SOURCE_SCOPE_FORBIDDEN'):adapter.validate_citation(rag,wrong,'course-default')
    with pytest.raises(AppError,match='SOURCE_SCOPE_FORBIDDEN'):
        adapter.validate_citation(rag,{**public,'scopeOrigin':{'user_id':'account-other','course_id':original.course_id}},'course-default')
    extra=next(s for s in rag.sources(original) if 'UNLISTED_OTHER' in s['quote'])
    alias=adapter.public_id(original,extra['id'])
    with pytest.raises(AppError,match='SOURCE_NOT_FOUND'):adapter.read(rag,alias,'course-default')
    response=client.post('/api/platform/rag/search',headers=alice,json={'query':'UNLISTED_OTHER_COURSE_7263',
        'documentIds':[extra['documentId']],'mode':'lexical'})
    assert not response.json()['evidence']['sources']
    assert not client.post('/api/platform/rag/validate',headers=alice,json={'citation':{**extra,'id':alias}}).json()['valid']


def test_duplicate_approved_imports_are_one_hit_but_keep_independent_aliases(library):
    app,client,original,document,_=library;p,rag=app.state.platform,app.state.rag
    duplicate=Scope(user_id=p.user_id,course_id='z-duplicate-preset')
    p.repo.ensure_course(p.user_id,{'id':duplicate.course_id,'name':'同内容副本'})
    state=asyncio.run(completed(p,rag.upload(duplicate,MATERIAL.read_bytes(),MATERIAL.name,'duplicate')))
    assert state['status']=='succeeded'
    adapter=ScopeAdapter(p,account_owner(app.state.account.find('alice')[0]))
    real=rag.sources(original,document_ids=[document['id']])
    selected=[s for s in adapter.sources(rag,'course-default') if s.get('isPlatform')]
    assert len(selected)==len(real)
    assert all(s['scopeOrigin']['course_id']==original.course_id for s in selected)
    twin=rag.sources(duplicate)[0]
    duplicate_alias=adapter.public_id(duplicate,twin['id'])
    assert adapter.read(rag,duplicate_alias,'course-default')['scopeOrigin']['course_id']==duplicate.course_id
    evidence=asyncio.run(adapter.search(rag,'course-default','循环队列 front rear',mode='lexical',budget=8000,limit=20))
    keys=[adapter.evidence_key(s) for s in evidence['sources']]
    assert len(keys)==len(set(keys)) and evidence['budget']['used']<=8000
    # Metadata projection never takes the caller's relabelled origin.
    with bind_owner(adapter.current_user_id):
        projected=public_api_value(p,{**selected[0],'originCourseId':'forged','originCourseName':'forged'})
    assert projected['originCourseId']==original.course_id and 'quote' not in projected


@pytest.mark.parametrize('mutation',['archive-course','archive-document','remove-document','unapproved-hash','unconfirmed-revision'])
def test_cross_course_citations_and_snapshots_fail_after_origin_changes(library,mutation):
    app,_,original,document,_=library;p,rag=app.state.platform,app.state.rag
    owner=account_owner(app.state.account.find('alice')[0]);adapter=ScopeAdapter(p,owner)
    public=next(s for s in adapter.sources(rag,'course-default') if s.get('isPlatform'))
    with bind_owner(owner):snapshot=app.state.agent.evidence_snapshot(p.scope(),[public])
    if mutation=='archive-course':
        p.repo.ensure_course(p.user_id,{'id':original.course_id,'name':'栈与队列公共教材','archived':True})
    elif mutation=='remove-document':rag.remove(original,document['id'],document['version'])
    else:
        row=p.repo.read(original,'document',document['id']);value=copy.deepcopy(row['value'])
        if mutation=='archive-document':value['archived']=True
        elif mutation=='unapproved-hash':value['fileHash']='f'*64
        else:value['knowledgeReview']={'confirmedRevision':value['contentRevision']-1}
        p.repo.put(original,'document',document['id'],value,row['version'])
    with pytest.raises(AppError):adapter.validate_citation(rag,public,'course-default')
    with bind_owner(owner):assert not app.state.agent.evidence_current(p.scope(),[public],snapshot)
    assert not adapter.sources(rag,'course-default')


def test_search_rechecks_cross_course_allowlist_after_external_await(library):
    app,_,original,document,_=library;p,rag=app.state.platform,app.state.rag
    owner=account_owner(app.state.account.find('alice')[0]);adapter=ScopeAdapter(p,owner)
    search=rag.search
    async def changing(scope,*args,**kwargs):
        result=await search(scope,*args,**kwargs)
        if scope==original:
            row=p.repo.read(original,'document',document['id'])
            # Keep isPlatform=True to prove that the six-file gate is checked
            # again using the request course, not the result's origin course.
            p.repo.put(original,'document',row['id'],{**row['value'],'fileHash':'f'*64,'isPlatform':True},row['version'])
        return result
    rag.search=changing
    result=asyncio.run(adapter.search(rag,'course-default','循环队列 front rear',mode='lexical'))
    assert not result['sources']


def test_mcp_fallback_does_not_resurrect_cross_course_sources_revoked_during_search(library):
    from backend.xueya.mcp_core import platform_registry
    app,_,original,document,_=library;p,rag=app.state.platform,app.state.rag
    owner=account_owner(app.state.account.find('alice')[0]);scope=Scope(user_id=owner,course_id='course-default')
    registry=platform_registry(p,scope,rag=rag)
    search=rag.search
    async def changing(origin,*args,**kwargs):
        result=await search(origin,*args,**kwargs)
        if origin==original:
            row=p.repo.read(original,'document',document['id'])
            p.repo.put(original,'document',row['id'],{**row['value'],'fileHash':'f'*64,'isPlatform':True},row['version'])
        return result
    rag.search=changing
    result=asyncio.run(registry.call('search_materials',{'query':'循环队列 front rear'}))
    assert not result.structured_content['data']['sources']


def test_approved_content_uploaded_privately_is_not_a_new_public_namespace(library):
    app,client,_,_,alice=library;p,rag=app.state.platform,app.state.rag
    reply=client.post('/api/platform/rag/upload?name=own-copy.md',headers={**alice,'Idempotency-Key':'own-approved-copy'},content=MATERIAL.read_bytes())
    assert reply.status_code==200
    job=reply.json()['job'];owner=account_owner(app.state.account.find('alice')[0])
    async def finish():
        p.jobs.stopped=False
        for _ in range(500):
            await p.jobs.tick();state=p.jobs.get(job['id'],owner)
            if state['status'] not in ('queued','running','cancelling'):return state
            await asyncio.sleep(.01)
        raise AssertionError('private parse did not complete')
    state=asyncio.run(finish());assert state['status']=='succeeded'
    private_id=state['result']['documentId']
    bobby=login(client,'bobby',True);bob_owner=account_owner(app.state.account.find('bobby')[0])
    bob=ScopeAdapter(p,bob_owner)
    assert all(s['documentId']!=private_id for s in bob.sources(rag,'course-default'))
    private_source=rag.sources(Scope(user_id=owner,course_id='course-default'),document_ids=[private_id])[0]
    guessed_alias=bob.public_id(Scope(user_id=owner,course_id='course-default'),private_source['id'])
    for source_id in (private_source['id'],guessed_alias):
        assert client.get('/api/platform/rag/read?sourceId='+source_id,headers=bobby).status_code>=400
    response=client.post('/api/platform/rag/search',headers=bobby,json={'query':'循环队列','mode':'lexical','documentIds':[private_id]})
    assert not response.json()['evidence']['sources']
