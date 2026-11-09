"""Private immutable mock papers, server time, saved answers and one-time grading."""
import copy
import time
import json
from pathlib import Path
from .common import require, digest, identifier, utc_now
from .practice_catalog import exam_bank
from .study_space_service import StudySpaceService, generate_id
from .objective_questions import TYPES, grade
from .rag_api import borrowed_api_permit

JOB='exam-assemble'


class ExamSessions:
    def __init__(self,app):
        self.app,self.p=app,app.state.platform
        self.service=StudySpaceService(self.p)
        self.p.jobs.register(JOB,self.generate)
        self.now=time.time

    def catalog(self,account):
        scope=self.service._scope(account)
        rows=[r for r in self.p.repo.all(scope,'artifact') if r.get('kind')=='exam-session']
        originals=json.loads((Path(__file__).with_name('data')/'exam408_sources.json').read_text(encoding='utf-8'))
        return {'sessions':[self.public(r) for r in rows], 'subjects':sorted({q['subject'] for q in exam_bank()['questions']}),
                'originalPapers':[{'year':year,**links,'verification':'高校索引链接已核对；PDF逐页内容和站内预览尚未验收'} for year,links in sorted(originals.items(),reverse=True)],
                'originalPaperStatus':'原卷与整理解析来自厦门工学院公开备考资料。站内固定题为改编/原创，不能冒充对应年份原题；原卷尚未结构化接入站内自动评分。',
                'jobs':[j for j in self.p.jobs.list(scope.user_id) if j['type']==JOB]}

    def candidates(self,value):
        subject=value.get('subject','')
        require(isinstance(subject,str) and len(subject)<=100,'INVALID_SUBJECT')
        return [q for q in exam_bank()['questions'] if q['type']=='single' and (not subject or q['subject']==subject)]

    def create(self,account,value):
        pool=self.candidates(value)
        count=value.get('count',10);minutes=value.get('minutes',30)
        require(type(count) is int and 1<=count<=40 and len(pool)>=count,'INSUFFICIENT_EXAM_QUESTIONS')
        require(type(minutes) is int and 1<=minutes<=180,'INVALID_EXAM_DURATION')
        value={**value,'count':count,'minutes':minutes}
        operation=identifier(value.get('operationId'));scope=self.service._scope(account)
        if value.get('mode')=='ai':
            require(bool(self.app.state.config.api_key),'AI_UNAVAILABLE')
            return {'job':self.p.jobs.submit(scope.user_id,{'type':JOB,'courseId':scope.course_id,
                'resource':'api','maxAttempts':1,'idempotencyKey':operation,
                'input':{'account':account,'request':value}})}
        require(value.get('mode','fixed')=='fixed','INVALID_EXAM_MODE')
        # Stable selection for a request; repeated requests never create new papers.
        ordered=sorted(pool,key=lambda q:digest([operation,q['id']]))
        return {'session':self.save(account,value,ordered[:count],'程序选编模拟卷')}

    def save(self,account,value,questions,label,assembly=None):
        scope=self.service._scope(account)
        key='exam-'+digest(value['operationId'])[:40]
        with self.p.db.transaction():
            previous=self.p.repo.read(scope,'artifact',key)
            if previous:
                require(previous['value']['request']==value,'IDEMPOTENCY_CONFLICT')
                return self.public(previous['value'])
            paper={'id':key,'kind':'exam-session','account':account,'request':value,'label':label,'status':'ready',
                   'minutes':value['minutes'],'questions':copy.deepcopy(questions),'answers':{},
                   'assembly':assembly or {'method':'program-selection','selectedCount':len(questions)},
                   'createdAt':utc_now(),'bankVersion':exam_bank()['version'],'revision':1}
            self.p.repo.put(scope,'artifact',key,paper,0)
        return self.public(paper)

    async def generate(self,scope,args,*,progress,checkpoint,commit):
        require(scope==self.service._scope(args['account']),'AUTH_SCOPE_MISMATCH')
        request=args['request'];pool=self.candidates(request)
        subjects=sorted({q['subject'] for q in pool})
        groups=[[q for q in pool if q['subject']==subject] for subject in subjects]
        candidates=[]
        for index in range(max(len(group) for group in groups)):
            for group in groups:
                if index<len(group):candidates.append(group[index])
        candidates=candidates[:max(16,min(120,request['count']*4))]
        with borrowed_api_permit(self.p):
            value=await self.service.model_json(args['account'],self.app.state.provider,
                f"从给定408固定题候选中按专题覆盖选题。必须恰好选择{request['count']}道题，questionIds长度必须等于{request['count']}，不允许多选。仅返回JSON对象questionIds数组，不改题，不虚构ID，不能称为历年真题。",
                {'requiredCount':request['count'],'count':request['count'],'candidates':[{'id':q['id'],'subject':q['subject'],'topic':q['topic'],'title':q['title']} for q in candidates]})
        ids=value.get('questionIds')
        selected=self.select_recommendations(candidates,ids,request['count'])
        normalized=len(ids)!=request['count']
        label='AI推荐＋程序配额选编模拟卷（非真题卷）' if normalized else 'AI选题模拟卷（固定题快照，非真题卷）'
        return commit(lambda:{'session':self.save(args['account'],request,selected,label,
            {'method':'ai-candidates-program-quota' if normalized else 'ai-selection',
             'recommendedCount':len(ids),'selectedCount':len(selected),'recommendedIds':ids})})

    @staticmethod
    def select_recommendations(pool,ids,count):
        known={q['id']:q for q in pool}
        require(isinstance(ids,list) and count<=len(ids)<=120
                and all(isinstance(i,str) and i in known for i in ids)
                and len(set(ids))==len(ids),'AI_INVALID_RESPONSE')
        if len(ids)==count:return [known[i] for i in ids]
        # Extra valid recommendations remain a candidate pool, never extra exam
        # questions. Round-robin by subject retains AI rank within each subject.
        groups={}
        for ident in ids:groups.setdefault(known[ident]['subject'],[]).append(known[ident])
        selected=[]
        for index in range(max(map(len,groups.values()))):
            for group in groups.values():
                if index<len(group):selected.append(group[index])
                if len(selected)==count:return selected

    def public(self,paper):
        submitted=paper['status']=='submitted'
        result={k:copy.deepcopy(paper[k]) for k in ('id','label','status','minutes','answers','createdAt','revision','startedAt','deadline','result','bankVersion','assembly') if k in paper}
        result['serverNow']=self.now()
        result['questions']=[{k:copy.deepcopy(q[k]) for k in ('id','title','prompt','type','subject','topic','options') if k in q} for q in paper['questions']]
        if submitted:
            for public,q in zip(result['questions'],paper['questions']):
                public.update(answer=q['answer'],explanation=q.get('explanation',''))
        return result

    def load(self,account,key):
        scope=self.service._scope(account)
        row=self.p.repo.read(scope,'artifact',identifier(key))
        require(row and row['value'].get('kind')=='exam-session','EXAM_NOT_FOUND')
        return scope,row

    def finish(self,paper):
        results=[]
        for q in paper['questions']:
            answer=paper['answers'].get(q['id'])
            result=grade(q,answer) if answer is not None else {'status':'unanswered','score':0,'maxScore':1}
            results.append({'questionId':q['id'],**result})
            if answer is not None:
                scope=self.service._scope(paper['account'])
                question_id='exam-q-'+digest([paper['id'],q['id'],paper['bankVersion']])[:40]
                if not self.p.repo.read(scope,'question',question_id):
                    snapshot={**copy.deepcopy(q),'id':question_id,'prompt':q.get('prompt') or q['title'],
                              'sourceType':'fixed','originalQuestionId':q['id'],'sourceRevision':paper['bankVersion'],
                              'examId':paper['id'],'createdAt':utc_now()}
                    self.p.repo.put(scope,'question',question_id,snapshot,0)
                saved=self.app.state.space_quiz.submit_attempt(paper['account'],{'questionId':question_id,
                    'questionRevision':1,'answer':answer,'operationId':'exam-attempt-'+digest([paper['id'],q['id']])[:40]})
                results[-1]['attemptId']=saved['id']
        paper.update(status='submitted',submittedAt=utc_now(),result={'score':sum(r['score'] for r in results),
            'maxScore':len(results),'questions':results,'method':'objective-server','unanswered':sum(r['status']=='unanswered' for r in results)})

    def operate(self,account,key,action,value=None):
        with self.p.db.transaction():
            scope,row=self.load(account,key);paper=row['value'];changed=False
            if paper['status']=='running' and self.now()>=paper['deadline']:
                self.finish(paper);changed=True
            if action!='read' and paper['status']!='submitted':
                require(value.get('expectedRevision')==row['version'],'EXAM_REVISION_CONFLICT')
                if action=='start':
                    require(paper['status']=='ready','EXAM_ALREADY_STARTED')
                    paper.update(status='running',startedAt=self.now(),deadline=self.now()+paper['minutes']*60);changed=True
                elif action=='answers':
                    require(paper['status']=='running','EXAM_NOT_STARTED')
                    answers=value.get('answers');require(isinstance(answers,dict),'INVALID_ANSWER')
                    known={q['id']:q for q in paper['questions']}
                    for ident,answer in answers.items():
                        require(ident in known,'QUESTION_NOT_IN_EXAM');grade(known[ident],answer)
                    paper['answers'].update(answers);changed=True
                elif action=='submit':
                    require(paper['status']=='running','EXAM_NOT_STARTED');self.finish(paper);changed=True
                else:require(False,'INVALID_EXAM_ACTION')
            if changed:
                paper['revision']=row['version']+1
                self.p.repo.put(scope,'artifact',key,paper,row['version'])
            return self.public(paper)
