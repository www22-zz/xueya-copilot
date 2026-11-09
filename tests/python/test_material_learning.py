import asyncio
import json
from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.config import Config


class Model:
    calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        value = json.loads(messages[1]['content'])
        if 'resources' in value:
            return {'model':'controlled','content':json.dumps({'tasks':[
                {'key':'queue','title':'复习队列','subject':'数据结构','phase':'理解与巩固','minutes':30,
                 'questionId':value['resources'][0]['questionId']} ]},ensure_ascii=False)}
        if 'candidates' in value:
            return {'model':'controlled','content':json.dumps({'questionIds':[q['id'] for q in value['candidates'][:value['count']]]})}
        ref = value['sources'][0]['id']
        return {'model': 'controlled', 'content': json.dumps({'concepts': [{
            'label': '队列', 'description': '先进先出', 'sourceIds': [ref], 'questions': [
                {'type': 'single', 'prompt': '队列是什么顺序？', 'options': ['FIFO', 'LIFO'], 'answer': 0, 'explanation': '先进先出'},
                {'type': 'multiple', 'prompt': '哪些是队列相关概念？', 'options': ['队头', '队尾', '树根'], 'answer': [0, 1], 'explanation': '队头队尾'},
                {'type': 'boolean', 'prompt': '队列是先进先出？', 'answer': True, 'explanation': 'FIFO'},
                {'type': 'fill', 'prompt': '队列顺序是____', 'answer': [['FIFO', '先进先出']], 'explanation': '先进先出'}]}]}, ensure_ascii=False)}


def test_upload_automatically_generates_persistent_material_questions(tmp_path,http_root):
    model=Model()
    app=create_app(Config(root=http_root,data_dir=tmp_path/'data',api_key='controlled',
                          preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        response=client.post('/api/platform/library/text',json={'courseId':'course-default','title':'队列讲义',
             'text':'# 队列\n'+('队列具有先进先出性质，队头出队，队尾入队。\n'*60),'idempotencyKey':'upload-material'})
        assert response.status_code==200,response.text

        async def complete():
            p=app.state.platform;p.jobs.stopped=False
            for _ in range(300):
                await p.jobs.tick()
                jobs=p.db.all("SELECT status FROM jobs")
                if jobs and all(j['status'] not in ('queued','running','cancelling') for j in jobs):break
                await asyncio.sleep(.01)
        asyncio.run(complete())
        reply=client.get('/api/learning/space/materials').json()
        assert reply['ok'],reply
        assert client.get('/api/learning/space/materials?courseId=not-owned-course').status_code!=200
        material=reply['materials'][0]
        assert material['status']=='succeeded',material
        assert material['coverage']['questions']==4
        ids=material['concepts'][0]['questionIds']
        for ident in ids:
            q=client.get('/api/learning/space/quiz/question/'+ident).json()['question']
            assert 'answer' not in q and 'explanation' not in q
        repeat=client.post('/api/learning/space/materials/prepare',json={
            'documentId':material['documentId'],'sourceCourseId':'course-default'})
        assert repeat.status_code==200,repeat.text
        assert repeat.json()['job']['id']==material['jobId'] and model.calls==1
        duplicate=client.post('/api/platform/library/text',json={'courseId':'course-default','title':'队列讲义副本',
             'text':'# 队列\n'+('队列具有先进先出性质，队头出队，队尾入队。\n'*60),'idempotencyKey':'upload-material-duplicate'})
        assert duplicate.status_code==200,duplicate.text
        asyncio.run(complete())
        assert model.calls==1
        assert len(client.get('/api/learning/space/materials').json()['materials'])==1
        client.post('/api/account/register',json={'username':'bob','password':'Fixture123','confirmPassword':'Fixture123'})
        assert client.get('/api/learning/space/materials').json()['materials']==[]
        assert client.get('/api/learning/space/quiz/question/'+ids[0]).status_code!=200


def test_model_cannot_publish_long_material_verbatim_as_graph_description(tmp_path,http_root):
    class LeakyModel(Model):
        async def generate(self,messages,**kwargs):
            reply=await super().generate(messages,**kwargs)
            value=json.loads(reply['content'])
            value['concepts'][0]['description']=max(json.loads(messages[1]['content'])['sources'],key=lambda row:len(row['text']))['text']
            reply['content']=json.dumps(value,ensure_ascii=False)
            return reply
    model=LeakyModel()
    app=create_app(Config(root=http_root,data_dir=tmp_path/'data',api_key='controlled',
                          preserve_legacy_data=True,auto_import_demo=False),provider=model,start_jobs=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/account/register',json={'username':'alice','password':'Fixture123','confirmPassword':'Fixture123'})
        client.headers['X-Xueya-Token']=client.get('/api/platform/bootstrap').json()['token']
        client.post('/api/platform/library/text',json={'courseId':'course-default','title':'队列讲义',
             'text':'# 队列\n'+('队列具有先进先出性质，队头出队，队尾入队。\n'*60),'idempotencyKey':'leaky-upload'})
        async def complete():
            p=app.state.platform;p.jobs.stopped=False
            for _ in range(300):
                await p.jobs.tick()
                if all(j['status'] not in ('queued','running') for j in p.db.all('SELECT status FROM jobs')):break
                await asyncio.sleep(.01)
        asyncio.run(complete())
        material=client.get('/api/learning/space/materials').json()['materials'][0]
        # The shared API queue conservatively marks post-dispatch errors unknown;
        # it must retain the precise rejection and never publish/retry the output.
        assert material['status']=='unknown' and material['error']=='MATERIAL_VERBATIM_OUTPUT'
        assert not material['concepts']
        assert not client.get('/api/learning/space/quiz/list').json()['questions']
        assert model.calls==1
