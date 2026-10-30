import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from backend.xueya.agent import Agent
from backend.xueya.config import Config
from backend.xueya.provider import MimoProvider
from backend.xueya.rag_search import definition_subject, lexical


@pytest.mark.parametrize('query', ['树的概念是什么', '树的基本概念是什么？', '树的定义是什么？', '什么叫树？'])
def test_tree_concept_queries_find_definition_without_concept_keyword(query):
    assert definition_subject(query) == '树'
    sources = [
        {'id': 'exercise', 'title': '教材', 'quote': '解释概念是什么，练习中说树的概念。'*10},
        {'id': 'outline', 'title': '教材', 'quote': '本章概述：树的定义及其他术语。'},
        {'id': 'definition', 'title': '教材', 'quote': '1. 树的定义\n树（tree）是结点的有限集合，非空树有唯一的根，其余结点分成互不相交的子树。'}]
    assert lexical(query, sources)[0][1]['id'] == 'definition'


async def test_chat_timeout_is_explicit_unknown_and_not_retried(platform):
    source = {'id': 'tree', 'title': '树', 'location': '第142页', 'quote': '树是有层次关系的结构。树有唯一的根结点。', 'keywords': ['树']}
    platform.repo.put(platform.scope(), 'source', 'tree', source)
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('controlled timeout', request=request)
    provider = MimoProvider(Config(api_key='offline-only'), platform, httpx.MockTransport(timeout))
    result = [e async for e in Agent(provider, platform).workflow({'question': '树的概念是什么', 'sources': [source]})][-1]
    assert result['reason'] == 'AI_TIMEOUT' and result['answerStatus'] == 'unavailable'
    assert '超时' in result['answer'] and '没有自动重试' in result['answer']
    assert len(calls) == 1 and platform.db.one('SELECT status FROM invocations')['status'] == 'unknown'
    assert platform.repo.read(platform.scope(), 'run', result['runId'])['value']['status'] == 'failed'


def test_current_ask_route_keeps_recording_through_render_and_transcribes_only_to_draft():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for the existing frontend component')
    js = r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('frontend/js/services/composer-input.js','utf8');
function harness(view='ask'){
 const calls=[],notices=[],state={courseId:'course-a',sessionId:'session-a',view,draft:'原草稿',pending:false};
 let stopPromise,stopped=0,saved=0,voice,deny=false;
 const stream={getTracks:()=>[{stop(){stopped++;}}]};
 class Recorder{
  static isTypeSupported(){return true;}
  constructor(){this.state='inactive';this.mimeType='audio/webm';}
  start(){this.state='recording';}
  stop(){this.state='inactive';this.ondataavailable?.({data:new Blob([new Uint8Array([1,2])])});stopPromise=this.onstop?.();}
 }
 class Audio{async decodeAudioData(){return{length:32000,duration:2};}async close(){}}
 class Offline{createBufferSource(){return{connect(){},start(){}};}async startRendering(){return{getChannelData:()=>new Float32Array(32000)};}}
 const window={MediaRecorder:Recorder,addEventListener(){},XueyaPlatform:{available:true,async learningRequest(path,options){
  calls.push([path,options]);if(path.startsWith('media/upload'))return{id:'media-a',version:1,endMs:2000};
  if(path==='media/transcribe')return{text:'树的定义是什么？'};throw Error('unexpected request');
 }}};
 const context={window,navigator:{mediaDevices:{getUserMedia:async()=>{if(deny)throw Object.assign(Error('denied'),{name:'NotAllowedError'});return stream;}}},
 MediaRecorder:Recorder,AudioContext:Audio,OfflineAudioContext:Offline,Blob,File,ArrayBuffer,DataView,Float32Array,AbortController,DOMException,URLSearchParams,
 setInterval(){return 1;},clearInterval(){},setTimeout(){return 2;},clearTimeout(){},document:{querySelector(){return{focus(){}};}}};
 vm.runInNewContext(source,context);
 voice=window.XueyaComposerInput.create({state,persist(){saved++;},render(){voice.mount();},toast(x){notices.push(x);}});
 return{voice,state,calls,notices,get stopped(){return stopped;},get saved(){return saved;},deny(){deny=true;},async settled(){await stopPromise;}};
}
(async()=>{
 for(const route of ['ask','overview','chat']){
  const h=harness(route);await h.voice.toggle();assert.equal(h.voice.status.phase,'recording',route);
  h.voice.mount();assert.equal(h.voice.busy,true);assert.equal(h.calls.length,0);
  await h.voice.toggle();await h.settled();assert.equal(h.voice.status.phase,'idle');
  assert.equal(h.state.draft,'原草稿\n树的定义是什么？');assert.equal(h.saved,1);assert.ok(h.stopped>0);
  assert.equal(h.calls.length,2);assert.ok(h.calls[0][0].startsWith('media/upload'));
  assert.equal(h.calls[1][0],'media/transcribe');assert.equal(h.calls[0][1].headers['Content-Type'],'audio/wav');
  const wav=new DataView(await h.calls[0][1].body.arrayBuffer());assert.equal(wav.getUint32(24,true),16000);assert.equal(wav.getUint16(22,true),1);
  assert.equal(h.state.pending,false); // Transcription never sends the draft as chat.
 }
 const changed=harness();await changed.voice.toggle();changed.state.view='knowledge';changed.voice.mount();await changed.settled();
 assert.equal(changed.voice.status.phase,'idle');assert.equal(changed.calls.length,0);assert.equal(changed.state.draft,'原草稿');assert.ok(changed.stopped>0);
 const denied=harness();denied.deny();await denied.voice.toggle();assert.equal(denied.voice.status.phase,'error');assert.ok(denied.voice.status.error.includes('麦克风'));assert.equal(denied.calls.length,0);
})();
'''
    result = subprocess.run([node, '-e', js], cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
