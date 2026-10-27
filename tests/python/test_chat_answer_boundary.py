import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from backend.xueya.agent import Agent
from backend.xueya.chat_policy import assistant_identity_question
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider


@pytest.mark.parametrize('question', ['你的大语言模型是？', '你的模型是？', '你用的是什么模型？',
    '请问你使用什么语言模型？', '你是谁？', '你是ChatGPT吗？', 'What model are you?', 'Which LLM do you use?'])
async def test_identity_uses_host_config_without_search_or_model(platform, monkeypatch, question):
    platform.repo.put(platform.scope(), 'source', 'model-word', {'id': 'model-word', 'title': '数据模型',
        'quote': '很多实际问题抽象的数据模型是树结构。大语言模型课程内容。', 'location': '第1页'})
    class Model:
        config = Config(api_key='offline-only', model='mimo-v2.6-flash')
        async def stream(self, *args, **kwargs):
            pytest.fail('Assistant identity must not call the text provider')
            yield
    def no_search(*args, **kwargs):
        pytest.fail('Model identity must not search the course')
    monkeypatch.setattr('backend.xueya.agent.retrieve', no_search)
    result = [e async for e in Agent(Model(), platform).workflow({'question': question})][-1]
    assert result['engine'] == 'assistant-info'
    assert 'mimo-v2.6-flash' in result['answer'] and '小米 MiMO' in result['answer']
    assert result['sources'] == result['sourceDetails'] == []
    assert result['timings']['modelCalls'] == 0


@pytest.mark.parametrize('question', ['教材中数据模型是什么？', '你能解释一下线性模型吗？',
    '你用什么模型定义线性表？', '根据教材，你的模型是？'])
def test_course_model_questions_are_not_assistant_identity(question):
    assert not assistant_identity_question(question)


async def test_generation_failure_keeps_reference_separate_from_answer(platform):
    source = {'id': 'queue-source', 'title': '队列', 'location': '第2页',
        'quote': '队列是先进先出的线性表。入队在队尾进行，出队在队头进行。'*20, 'keywords': ['队列']}
    platform.repo.put(platform.scope(), 'source', source['id'], source)
    calls = []
    def unavailable(request):
        calls.append(request)
        return httpx.Response(503)
    provider = MimoProvider(Config(api_key='offline-only'), platform, httpx.MockTransport(unavailable))
    events = [e async for e in Agent(provider, platform).workflow({'question': '根据教材解释队列', 'sources': [source]})]
    result = events[-1]
    assert result['answerStatus'] == 'unavailable' and result['verification'] == 'not-generated'
    assert '未能完成' in result['answer'] and len(result['answer']) < 150
    assert source['quote'] not in result['answer'] and '根据当前资料，可以' not in result['answer']
    assert result['sourceDetails'][0]['id'] == source['id']
    assert result['sourceDetails'][0]['quote'] == source['quote']
    assert len(calls) == 1  # An upstream failure is not retried.


def test_browser_uses_server_citations_and_does_not_dump_text_on_network_failure():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to execute the existing frontend module')
    source = r'''
const assert=require('node:assert/strict');
const {createChatService}=require('./frontend/js/services/chat-service.js');
(async()=>{
 const fresh={id:'new-server-hit',title:'教材',quote:'队列在队尾入队，在队头出队。',location:'实际第92页',documentId:'book',keywords:['队列']};
 const result={type:'done',ok:true,engine:'xiaomi-mimo',answer:'可以把队列看成排队：从队尾加入，从队头离开。 [1]',sources:[fresh.id],sourceDetails:[fresh,{...fresh,id:'not-cited'}]};
 const service=createChatService({fetchImpl:async()=>new Response('data: '+JSON.stringify(result)+'\n\n',{headers:{'Content-Type':'text/event-stream'}})});
 const answer=await service.stream({question:'队列是什么？',sources:[]},{workflow:true});
 assert.deepEqual(answer.sources,[fresh]);assert.equal(answer.online,true);
 const failing=createChatService({fetchImpl:async()=>new Response('',{status:503})});
 const failed=await failing.stream({question:'队列是什么？',sources:[fresh]},{workflow:true});
 assert.equal(failed.answerStatus,'unavailable');assert.equal(failed.engine,'回答未完成');
 assert.equal(failed.answer.includes(fresh.quote),false);assert.equal(failed.online,false);
 const infoService=createChatService({fetchImpl:async()=>new Response('data: '+JSON.stringify({type:'done',ok:true,answer:'当前模型是小米MiMO。',sources:[],engine:'assistant-info'})+'\n\n',{headers:{'Content-Type':'text/event-stream'}})});
 const info=await infoService.stream({question:'你的大语言模型是？',sources:[]},{workflow:true});
 assert.equal(info.engine,'应用信息');assert.equal(info.sources.length,0);assert.equal(info.online,false);
})();
'''
    checked = subprocess.run([node, '-e', source], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


def test_browser_preserves_pdf_and_web_citations_across_compatible_response_fields():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to execute the existing frontend module')
    source = r'''
const assert=require('node:assert/strict');
const {createChatService}=require('./frontend/js/services/chat-service.js');
(async()=>{
 const pdf={id:'pdf-fresh',title:'教材',quote:'队列遵循先进先出。',location:'PDF第92页',documentId:'book'};
 const web={id:'web-example',title:'网页',quote:'队列遵循先进先出。',location:'https://example.com/queue',url:'https://example.com/queue',isWeb:true};
 const extra={...web,id:'not-cited'};
 for(const payload of [
   {sources:[pdf.id,web.id],sourceDetails:[pdf],sourceObjects:[web,extra]},
   {sources:[web.id],sourceDetails:[],sourceObjects:[web,extra]}
 ]){
   const result={type:'done',ok:true,engine:'xiaomi-mimo',answer:'队列遵循先进先出。 [1]',...payload};
   const service=createChatService({fetchImpl:async()=>new Response('data: '+JSON.stringify(result)+'\n\n',{headers:{'Content-Type':'text/event-stream'}})});
   const answer=await service.stream({question:'队列是什么？',sources:[],webSearch:true},{workflow:true});
   assert.deepEqual(answer.sources,payload.sources.length===2?[pdf,web]:[web]);
   assert.equal(answer.sources.at(-1).url,web.url);
   assert.equal(answer.sources.some(s=>s.id===extra.id),false);
 }
})();
'''
    checked = subprocess.run([node, '-e', source], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


async def test_document_scope_searches_beyond_browser_preview_and_first_48_sources(platform):
    for n in range(60):
        platform.repo.put(platform.scope(), 'source', f'a-{n:02}', {'id': f'a-{n:02}', 'documentId': 'book',
            'title': '教材', 'quote': '这部分只讲顺序表。', 'location': '第1页'})
    correct = {'id': 'z-stack', 'documentId': 'book', 'title': '教材', 'location': '第84页',
               'quote': '栈是后进先出的线性表。栈的插入和删除都在栈顶进行。', 'keywords': ['栈']}
    platform.repo.put(platform.scope(), 'source', correct['id'], correct)
    messages = []
    class Model:
        config = Config(api_key='offline-only')
        async def stream(self, value, **kwargs):
            messages.append(value)
            yield {'type': 'content', 'text': json.dumps({'answer': correct['quote'], 'sources': [correct['id']],
                'claims': [{'text': correct['quote'], 'evidence': [{'sourceId': correct['id'], 'quote': correct['quote']}]}]})}
    result = [e async for e in Agent(Model(), platform).workflow({'question': '栈是什么？', 'documentIds': ['book'],
        'context': {'library': [{'id': 'a-00', 'quote': '过时的浏览器预览。'}]}})][-1]
    assert result['sources'] == [correct['id']]
    assert result['sourceDetails'][0]['id'] == correct['id']
    materials = json.loads(messages[0][-1]['content'])['materials']
    assert materials[0]['id'] == correct['id']


def test_definition_question_prefers_defining_prose_over_dense_stack_code():
    from backend.xueya.rag_search import lexical
    sources = [
        {'id': 'code', 'title': '教材', 'page': 88, 'quote': '栈 stack 入栈代码 push 出栈 pop 空栈 '*20},
        {'id': 'definition', 'title': '教材', 'page': 84, 'quote': '1. 栈的定义\n栈（stack）是限定仅在表的一端进行插入和删除操作的线性表。'}]
    assert lexical('栈是什么？', sources)[0][1]['id'] == 'definition'
    assert lexical('什么是栈？', sources)[0][1]['id'] == 'definition'
    assert lexical('栈的入栈代码', sources)[0][1]['id'] == 'code'


async def test_multiple_spans_in_one_paragraph_show_one_source_number():
    from backend.agent.answer_policy import finalize_answer
    source = {'id': 'queue', 'title': '队列', 'location': '第92页', 'quote': '队列遵循先进先出。入队在队尾进行。'}
    value = {'answer': '概括', 'sources': ['queue'], 'claims': [{'text': '队列从队尾加入新元素，先来的先离开。',
        'evidence': [{'sourceId': 'queue', 'quote': '队列遵循先进先出。'}, {'sourceId': 'queue', 'quote': '入队在队尾进行。'}]}]}
    result = await finalize_answer(json.dumps(value), [source], 'controlled', review=lambda *a, **k: {'supported': True})
    assert result['answer'].count('[1]') == 1
    assert len(result['claims'][0]['evidence']) == 2
