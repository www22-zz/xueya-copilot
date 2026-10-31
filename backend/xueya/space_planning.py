"""Conversation planning intake and durable generation over the shared services."""
import copy
import datetime
import re
from zoneinfo import ZoneInfo

from .common import digest, identifier, require, utc_now
from .rag_api import borrowed_api_permit
from .study_space_service import StudySpaceService

JOB = 'space-plan-generate'


def number(text):
    if text.isdigit():return int(text)
    digits={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    if text=='十':return 10
    if '十' in text:
        tens,units=text.split('十',1)
        return digits.get(tens,1)*10+digits.get(units,0)
    return digits.get(text)


def planning_intent(text):
    if re.search(r'什么是|是什么意思|解释.{0,8}(?:规划|学习计划)|规划.{0,5}的(?:概念|定义)',text):return False
    return bool(re.search(r'(?:帮我|请|给我|制定|安排|生成).{0,25}(?:学习计划|复习计划|学习规划|规划|复习安排)|安排.{0,15}(?:学习|复习)',text))


def extract(text, today):
    values={}
    match=re.search(r'(?:学习|复习|掌握|备考)([^，。！？\n]{2,80})',text)
    if match:
        goal=re.split(r'每天|每日|每周|持续|截止|[，,]',match[1])[0].strip()
        if goal and not re.match(r'^(?:计划|规划|安排)',goal):values['goal']=goal
    for subject in ('数据结构','计算机组成原理','操作系统','计算机网络'):
        if subject in text:values['goal']=text[:200] if len([s for s in ('数据结构','计算机组成原理','操作系统','计算机网络') if s in text])>1 else subject
    match=re.search(r'([0-9一二两三四五六七八九十]+)\s*(天|周|星期|个月)',text)
    if match:
        count=number(match[1])
        if count:values['daysCount']=count*({'天':1,'周':7,'星期':7,'个月':30}[match[2]])
    match=re.search(r'(?:截止|到|截至)\s*(\d{4}-\d{2}-\d{2})',text)
    if match:
        try:values['daysCount']=(datetime.date.fromisoformat(match[1])-today).days+1
        except ValueError:pass
    match=re.search(r'(?:每天|每日)\s*([0-9一二两三四五六七八九十]+)\s*(分钟|小时)',text)
    if match:
        count=number(match[1])
        if count:values['dailyMinutes']=count*(60 if match[2]=='小时' else 1)
    if re.search(r'(?:每天|每日)\s*半(?:个)?小时',text):values['dailyMinutes']=30
    return values


class ConversationPlanning:
    def __init__(self, app):
        self.app,self.p=app,app.state.platform
        self.service=StudySpaceService(self.p)
        self.p.jobs.register(JOB,self.execute)

    def submit(self, account, value, *, session_id=None, origins=None, assumptions=None):
        require(isinstance(value.get('goal'),str) and 0<len(value['goal'])<=1000,'PLAN_GOAL_REQUIRED')
        require(type(value.get('daysCount')) is int and 1<=value['daysCount']<=366,'INVALID_PLAN_DATES')
        require(type(value.get('dailyMinutes')) is int and 15<=value['dailyMinutes']<=480,'INVALID_DAILY_MINUTES')
        conditions={key:value[key] for key in ('title','goal','daysCount','dailyMinutes','restDays','subjects') if key in value}
        scope=self.service._scope(account)
        return self.p.jobs.submit(scope.user_id,{'type':JOB,'courseId':scope.course_id,'resource':'api','maxAttempts':1,
            'idempotencyKey':identifier(value.get('operationId')),
            'input':{'account':account,'sessionId':session_id,'conditions':conditions,'origins':origins or {},'assumptions':assumptions or []}})

    def listing(self, account):
        return [job for job in self.p.jobs.list(self.service._scope(account).user_id) if job['type']==JOB][:20]

    def intake(self, account, value):
        scope=self.service._scope(account)
        key='planning-request-'+digest(identifier(value.get('operationId')))[:40]
        signature=digest(value)
        with self.p.db.transaction():
            prior=self.p.repo.read(scope,'artifact',key)
            if prior:
                require(prior['value']['signature']==signature,'IDEMPOTENCY_CONFLICT')
                return copy.deepcopy(prior['value']['result'])
            result=self._intake(account,value)
            if result['handled']:
                self.p.repo.put(scope,'artifact',key,{'kind':'planning-request','signature':signature,'result':result},0)
            return result

    def _intake(self, account, value):
        text=value.get('question')
        require(isinstance(text,str) and 0<len(text)<=4000,'INVALID_QUESTION')
        session=identifier(value.get('sessionId'))
        key='planning-intake-'+digest(session)[:40]
        scope=self.service._scope(account)
        old=self.p.repo.read(scope,'artifact',key)
        prior=old['value'] if old else {}
        today=datetime.datetime.now(ZoneInfo('Asia/Shanghai')).date()
        found=extract(text,today)
        defaults=value.get('useDefaults') is True or bool(re.search(r'按默认(?:条件)?安排|使用默认条件',text))
        followup=prior.get('status')=='collecting' and bool(found or defaults)
        if not planning_intent(text) and not followup:return {'handled':False}
        known=copy.deepcopy(prior.get('conditions',{}))
        origins=copy.deepcopy(prior.get('origins',{}))
        history=value.get('history',[])
        require(isinstance(history,list) and len(history)<=12,'INVALID_HISTORY')
        for message in [*history,{'role':'user','content':text}]:
            if isinstance(message,dict) and message.get('role')=='user' and isinstance(message.get('content'),str):
                for field,field_value in extract(message['content'][:4000],today).items():
                    known[field]=field_value;origins[field]={'type':'user-statement','text':message['content'][:4000]}
        assumptions=[]
        if defaults:
            for field,default in (('daysCount',28),('dailyMinutes',30)):
                if field not in known:
                    known[field]=default;origins[field]={'type':'user-selected-default'};assumptions.append(field)
        missing=[field for field in ('goal','daysCount','dailyMinutes') if field not in known]
        if not missing:
            require(type(known['daysCount']) is int and 1<=known['daysCount']<=366,'INVALID_PLAN_DATES')
            require(type(known['dailyMinutes']) is int and 15<=known['dailyMinutes']<=480,'INVALID_DAILY_MINUTES')
        intake={'kind':'planning-intake','sessionId':session,'conditions':known,'origins':origins,'assumptions':assumptions,
                'status':'collecting' if missing else 'ready','updatedAt':utc_now()}
        self.p.repo.put(scope,'artifact',key,intake,old['version'] if old else 0)
        labels={'goal':'学习目标','daysCount':'期限或持续天数','dailyMinutes':'每天可用分钟数'}
        summary='；'.join(f'{labels[field]}：{known[field]}' for field in known)
        if missing:
            return {'handled':True,'status':'collecting','conditions':known,'missing':missing,
                    'answer':('已记下：'+summary+'。' if known else '')+'还需要'+'、'.join(labels[f] for f in missing)+'。你也可以主动选择“按默认条件安排”（4周、每天30分钟，已有条件优先）。'}
        job=self.submit(account,{**known,'operationId':value['operationId']},session_id=session,origins=origins,assumptions=assumptions)
        return {'handled':True,'status':'queued','conditions':known,'jobId':job['id'],'answer':summary+'。正在生成草稿；采用前不会进入执行待办。'}

    async def execute(self, scope, args, *, progress, checkpoint, commit):
        account=args['account']
        require(self.service._scope(account)==scope,'AUTH_SCOPE_MISMATCH')
        with borrowed_api_permit(self.p):
            progress({'percent':10,'label':'正在拆解目标与排程'})
            plan=await self.service.generate_model_plan(account,self.app.state.provider,args['conditions'])
            row=self.p.repo.read(scope,'plan',plan['id'])
            self.p.repo.put(scope,'plan',plan['id'],{**row['value'],'generationStatus':'framework-pending'},row['version'])
            checkpoint({'planId':plan['id'],'stage':'framework'})
            progress({'percent':60,'label':'草稿已保存，正在生成独立知识框架'})
            subject=next((s for s in ('数据结构','计算机组成原理','操作系统','计算机网络') if s in plan['goal']),'计算机基础')
            framework=await self.service.generate_model_framework(account,self.app.state.provider,subject,plan['goal'][:200])
        def save():
            row=self.p.repo.read(scope,'plan',plan['id']);saved=row['value']
            saved.update(frameworkId=framework['id'],sessionId=args['sessionId'],conditionsOrigin=args['origins'],assumptions=args['assumptions'],generationStatus='completed')
            self.p.repo.put(scope,'plan',plan['id'],saved,row['version'])
            row=self.p.repo.read(scope,'concept',framework['id']);fw=row['value']
            fw.update(planId=plan['id'],sessionId=args['sessionId'])
            self.p.repo.put(scope,'concept',framework['id'],fw,row['version'])
            return {'planId':plan['id'],'frameworkId':framework['id'],'sessionId':args['sessionId']}
        result=commit(save);progress({'percent':100,'label':'草稿与知识框架已保存，等待明确采用'})
        return result

    def status(self, account, job_id):
        job=self.p.jobs.get(identifier(job_id),self.service._scope(account).user_id)
        require(job and job['type']==JOB,'JOB_NOT_FOUND')
        return job
