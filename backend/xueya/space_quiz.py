"""One private Question/Attempt/Evaluation service for chat and practice views."""
import copy
import re
from .common import AppError, digest, dumps, identifier, require, utc_now
from .rag_api import borrowed_api_permit
from .study_space_service import StudySpaceService, generate_id

GENERATE='space-quiz-generate'
EVALUATE='space-quiz-evaluate'


class SpaceQuiz:
    def __init__(self,app):
        self.app,self.p=app,app.state.platform
        self.service=StudySpaceService(self.p)
        self.p.jobs.register(GENERATE,self.generate)
        self.p.jobs.register(EVALUATE,self.evaluate)

    def scope(self,account):return self.service._scope(account)

    @staticmethod
    def normalize(attempt,revision=None):
        value=copy.deepcopy(attempt)
        value.setdefault('revision',revision or value.get('version',1))
        value.setdefault('questionRevision',None)
        if 'evaluations' not in value:
            original=value.get('evaluation')
            value['evaluations']=[]
            if isinstance(original,dict):
                entry={'id':'legacy-evaluation-'+digest(value.get('id'))[:32], 'source':'legacy-assessment',
                       'status':original.get('status','unknown'),'createdAt':value.get('createdAt'), 'result':copy.deepcopy(original)}
                value['evaluations'].append(entry)
                if entry['status']=='graded':value['effectiveEvaluation']=copy.deepcopy(entry)
        return value

    def question(self,account,question_id):
        row=self.p.repo.read(self.scope(account),'question',identifier(question_id))
        require(row is not None,'QUESTION_NOT_FOUND')
        return {**row['value'],'revision':row['version']}

    def attempt(self,account,attempt_id):
        scope=self.scope(account);row=self.p.repo.read(scope,'attempt',identifier(attempt_id))
        require(row is not None,'ATTEMPT_NOT_FOUND')
        attempt=self.normalize({**row['value'],'id':row['id']},row['version']);changed=False
        for entry in attempt.get('evaluations',[]):
            if entry.get('status')=='queued' and entry.get('jobId'):
                job=self.p.jobs.get(entry['jobId'],scope.user_id)
                if job and job['status'] in ('failed','unknown','cancelled'):
                    entry.update(status=job['status'],completedAt=job['updatedAt']);changed=True
        if changed:
            attempt['revision']+=1;self.effective(attempt)
            self.p.repo.put(scope,'attempt',attempt['id'],attempt,row['version'])
        return attempt

    def listing(self,account):
        scope=self.scope(account)
        questions=[{**self.service.public_question(q),'revision':q['version']} for q in self.p.repo.all(scope,'question')]
        attempts=[self.attempt(account,row['id']) for row in self.p.repo.all(scope,'attempt')]
        attempts.sort(key=lambda row:row.get('createdAt',''),reverse=True)
        jobs=[job for job in self.p.jobs.list(scope.user_id) if job['type'] in (GENERATE,EVALUATE)]
        return {'questions':questions,'attempts':[self.public_attempt(a) for a in attempts],'jobs':jobs}

    @staticmethod
    def public_attempt(attempt):
        attempt=SpaceQuiz.normalize(attempt)
        result={key:copy.deepcopy(attempt[key]) for key in ('id','questionId','questionRevision','answer','evaluations','effectiveEvaluation','revision','createdAt') if key in attempt}
        if attempt.get('questionSnapshot'):result['questionSnapshotView']=StudySpaceService.public_question(attempt['questionSnapshot'])
        result['canReview']=bool(attempt.get('questionSnapshot',{}).get('prompt'))
        return result

    def receipt(self,scope,key,request,operation):
        key='quiz-operation-'+digest(identifier(key))[:40]
        signature=digest(request)
        with self.p.db.transaction():
            previous=self.p.repo.read(scope,'artifact',key)
            if previous:
                require(previous['value']['signature']==signature,'IDEMPOTENCY_CONFLICT')
                return copy.deepcopy(previous['value']['result'])
            result=operation()
            self.p.repo.put(scope,'artifact',key,{'kind':'quiz-operation','signature':signature,'result':result},0)
            return result

    def submit_generation(self,account,value):
        subject=value.get('subject');kind=value.get('type','single')
        require(isinstance(subject,str) and 0<len(subject)<=100 and kind in ('single','short'),'INVALID_QUIZ_REQUEST')
        count=value.get('count',1);require(type(count) is int and 1<=count<=5,'INVALID_QUIZ_COUNT')
        scope=self.scope(account)
        return self.p.jobs.submit(scope.user_id,{'type':GENERATE,'courseId':scope.course_id,'resource':'api','maxAttempts':1,
            'idempotencyKey':identifier(value.get('operationId')),'input':{'account':account,'subject':subject,'type':kind,'count':count,'sessionId':value.get('sessionId')}})

    def chat(self,account,value):
        text=value.get('question');require(isinstance(text,str) and len(text)<=4000,'INVALID_QUESTION')
        if re.search(r'什么是|是什么意思|解释.{0,8}小测',text) or not re.search(r'(?:给我|出|来|生成|做).{0,12}(?:一道|一题|\d题|小测|测试题|单选题|主观题|练习题)',text):
            return {'handled':False}
        from .space_planning import number
        count_match=re.search(r'([0-9一二两三四五]+)\s*(?:道|题)',text)
        count=number(count_match[1]) if count_match else 1
        require(type(count) is int and 1<=count<=5,'INVALID_QUIZ_COUNT')
        # Fixed questions take priority when a unique, usable topic matches.
        if count==1 and not re.search(r'AI|生成|新题|主观',text,re.I):
            from .study_resources import match_task
            resource=match_task({'title':text})
            if resource['type']=='question':
                from .practice_bank import question as fixed
                from .practice_catalog import exam_question
                question=fixed(resource['questionId']) or exam_question(resource['questionId'])
                if question and question['type']=='single':
                    scope=self.scope(account)
                    if not self.p.repo.read(scope,'question',question['id']):
                        self.p.repo.put(scope,'question',question['id'],{**copy.deepcopy(question),'sourceType':'fixed','sourceRevision':resource['version'],'createdAt':utc_now()},0)
                    return {'handled':True,'status':'succeeded','questionIds':[question['id']]}
        kind='short' if re.search(r'主观|简答|综合',text) else 'single'
        job=self.submit_generation(account,{'subject':text[:100],'type':kind,'count':count,'sessionId':value.get('sessionId'),'operationId':value.get('operationId')})
        return {'handled':True,'status':'queued','jobId':job['id']}

    async def generate(self,scope,args,*,progress,checkpoint,commit):
        require(self.scope(args['account'])==scope,'AUTH_SCOPE_MISMATCH')
        questions=[]
        with borrowed_api_permit(self.p):
            for index in range(args.get('count',1)):
                question=await self.service.generate_model_question(args['account'],self.app.state.provider,args['subject'],args['type'],previous_prompts=[q['prompt'] for q in questions])
                question.update(sessionId=args.get('sessionId'),createdAt=utc_now());questions.append(question)
                progress({'percent':round((index+1)*90/args.get('count',1)),'label':'正在校验小测题目'})
        require(len({q['prompt'] for q in questions})==len(questions),'DUPLICATE_QUIZ_QUESTION')
        def save():
            with self.p.db.transaction():
                for question in questions:self.p.repo.put(scope,'question',question['id'],question,0)
        commit(save)
        return {'questionIds':[q['id'] for q in questions]}

    def submit_attempt(self,account,value):
        scope=self.scope(account)
        def save():
            question=self.question(account,value.get('questionId'))
            require(type(value.get('questionRevision')) is int and value['questionRevision']==question['revision'],'QUESTION_REVISION_CONFLICT')
            answer=value.get('answer')
            if question['type']=='short':require(isinstance(answer,str) and 0<len(answer.strip())<=20000,'INVALID_ANSWER')
            else:self.service.grade_submission(question,answer)
            attempt={'id':generate_id('attempt-'),'questionId':question['id'],'questionRevision':question['revision'],
                'questionSnapshot':copy.deepcopy(question),'answer':copy.deepcopy(answer),'revision':1,'createdAt':utc_now(),'evaluations':[]}
            if question['type']=='short':
                evaluation={'id':generate_id('evaluation-'),'source':'ai-reference','status':'queued','createdAt':utc_now()}
                job=self.p.jobs.submit(scope.user_id,{'type':EVALUATE,'courseId':scope.course_id,'resource':'api','maxAttempts':1,
                    'idempotencyKey':'initial-'+attempt['id'],'input':{'account':account,'attemptId':attempt['id'],'evaluationId':evaluation['id']}})
                evaluation['jobId']=job['id'];attempt['evaluations'].append(evaluation)
            else:
                evaluation={'id':generate_id('evaluation-'),'source':'objective','status':'graded','createdAt':utc_now(),
                            'result':self.service.grade_submission(question,answer)}
                attempt['evaluations'].append(evaluation);attempt['effectiveEvaluation']=copy.deepcopy(evaluation)
            self.p.repo.put(scope,'attempt',attempt['id'],attempt,0)
            return self.public_attempt(attempt)
        return self.receipt(scope,value.get('operationId'),value,save)

    def submit_fixed(self,account,value):
        """Bridge fixed subjective questions to the same immutable assessment chain.

        Old self scores remain self scores. No client rubric or claimed score is
        accepted, no code is executed, and an unseen original PDF is not inferred.
        """
        from .practice_bank import bank,question as fixed_question
        from .practice_catalog import exam_bank,exam_question
        original_id=identifier(value.get('questionId'))
        fixed=fixed_question(original_id) or exam_question(original_id)
        require(fixed and fixed['type'] in ('short','code'),'SUBJECTIVE_QUESTION_REQUIRED')
        version=exam_bank()['version'] if fixed.get('bankSource')=='exam408' else bank()['version']
        question_id='fixed-'+digest([original_id,version])[:40]
        scope=self.scope(account)
        with self.p.db.transaction():
            if not self.p.repo.read(scope,'question',question_id):
                rubric=[]
                if fixed.get('selfScoreMode')!='mastery':
                    rubric=[{'id':p['id'],'description':p['label']+'：'+p['reference'],'points':p['points']} for p in fixed.get('parts',[])]
                reference=fixed.get('explanation','')+'\n'+str(fixed.get('answer',''))
                if fixed.get('solutions'):reference+='\n'+dumps(fixed['solutions'])
                question={'id':question_id,'type':'short','subject':fixed.get('subject','计算机基础'),
                    'prompt':fixed['title']+'\n'+fixed.get('prompt','')+'\n'+'\n'.join(p['label'] for p in fixed.get('parts',[])),
                    'explanation':reference,'rubric':rubric,'sourceType':'fixed-reference','originalQuestionId':original_id,
                    'sourceRevision':version,'createdAt':utc_now(),
                    'limitations':['AI仅使用保存的文字题干和参考，不运行代码，也没有读取嵌入原卷PDF的图或完整条件。参考点评不能冒充官方阅卷。']}
                self.p.repo.put(scope,'question',question_id,question,0)
            row=self.question(account,question_id)
            return self.submit_attempt(account,{'questionId':question_id,'questionRevision':row['revision'],'answer':value.get('answer'),'operationId':value.get('operationId')})

    def review(self,account,attempt_id,value,*,manual=False):
        scope=self.scope(account)
        def save():
            row=self.p.repo.read(scope,'attempt',identifier(attempt_id));require(row is not None,'ATTEMPT_NOT_FOUND')
            attempt=self.normalize({**row['value'],'id':row['id']},row['version'])
            require(type(value.get('expectedRevision')) is int and attempt['revision']==value['expectedRevision'],'ATTEMPT_REVISION_CONFLICT')
            reason=value.get('reason');require(isinstance(reason,str) and 0<len(reason.strip())<=2000,'REVIEW_REASON_REQUIRED')
            require(attempt.get('questionSnapshot',{}).get('prompt'),'QUESTION_SNAPSHOT_REQUIRED')
            question=attempt['questionSnapshot']
            entry={'id':generate_id('evaluation-'),'source':'human' if manual else 'ai-review','status':'graded' if manual else 'queued','reason':reason,'createdAt':utc_now()}
            if manual:
                result={'method':'human-correction','feedback':reason}
                if value.get('disputed') is True:
                    entry['status']='disputed'
                elif question['type']=='single':
                    require(type(value.get('correct')) is bool,'INVALID_CORRECTION')
                    result.update(correct=value['correct'],score=int(value['correct']),maxScore=1)
                elif question.get('rubric'):
                    maximum=sum(point['points'] for point in question['rubric']);score=value.get('score')
                    require(type(score) in (int,float) and 0<=score<=maximum,'INVALID_CORRECTION')
                    result.update(score=score,maxScore=maximum)
                else:
                    require('score' not in value,'RUBRIC_REQUIRED')
                entry['result']=result
            elif question['type']=='single':
                entry.update(status='graded',source='objective-recheck',result=self.service.grade_submission(question,attempt['answer']))
            else:
                require(not any(e['status']=='queued' for e in attempt['evaluations']),'EVALUATION_BUSY')
                job=self.p.jobs.submit(scope.user_id,{'type':EVALUATE,'courseId':scope.course_id,'resource':'api','maxAttempts':1,
                    'idempotencyKey':'review-'+entry['id'],'input':{'account':account,'attemptId':attempt_id,'evaluationId':entry['id']}})
                entry['jobId']=job['id']
            attempt['evaluations'].append(entry);attempt['revision']+=1
            self.effective(attempt)
            self.p.repo.put(scope,'attempt',attempt_id,attempt,row['version'])
            return self.public_attempt(attempt)
        return self.receipt(scope,value.get('operationId'),{'attemptId':attempt_id,'manual':manual,**value},save)

    @staticmethod
    def effective(attempt):
        completed=[e for e in attempt['evaluations'] if e['status'] in ('graded','disputed')]
        if completed:attempt['effectiveEvaluation']=copy.deepcopy(completed[-1])
        else:attempt.pop('effectiveEvaluation',None)

    async def evaluate(self,scope,args,*,progress,checkpoint,commit):
        account=args['account'];require(self.scope(account)==scope,'AUTH_SCOPE_MISMATCH')
        attempt=self.attempt(account,args['attemptId'])
        entry=next(e for e in attempt['evaluations'] if e['id']==args['evaluationId'])
        try:
            with borrowed_api_permit(self.p):
                result=await self.service.evaluate_model_answer(account,self.app.state.provider,attempt['questionSnapshot'],attempt['answer'],
                    review_reason=entry.get('reason'),previous=attempt.get('effectiveEvaluation'))
        except BaseException:
            # Keep the original answer and prior assessment. A paid result may
            # be unknown; no zero score and no implicit replay are introduced.
            self.finish_evaluation(scope,args,'unknown',None)
            raise
        commit(lambda:self.finish_evaluation(scope,args,'graded',result))
        return {'attemptId':attempt['id'],'evaluationId':entry['id']}

    def finish_evaluation(self,scope,args,status,result):
        with self.p.db.transaction():
            row=self.p.repo.read(scope,'attempt',args['attemptId']);require(row is not None,'ATTEMPT_NOT_FOUND')
            attempt=self.normalize(row['value'],row['version']);entry=next(e for e in attempt['evaluations'] if e['id']==args['evaluationId'])
            require(entry['status']=='queued','EVALUATION_ALREADY_FINAL')
            entry.update(status=status,completedAt=utc_now())
            if result is not None:entry['result']=result
            attempt['revision']+=1;self.effective(attempt)
            self.p.repo.put(scope,'attempt',attempt['id'],attempt,row['version'])
