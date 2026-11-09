"""Local weekly evidence capture, with explicit per-account external dispatch opt-in.

External dispatch is off by default. Only a confirmed settings mutation can
enable it; configured credentials alone never count as consent.
"""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .analysis_sources import content_fingerprint, source_options
from .common import AppError, digest, identifier, require

KEY='analysis-schedule'


class AnalysisSchedule:
    def __init__(self,analysis,*,clock=None):
        self.analysis,self.p=analysis,analysis.p
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.runner=None

    def next_due(self,now,settings):
        local=now.astimezone(ZoneInfo(settings['timezone']))
        hour,minute=map(int,settings['time'].split(':'))
        candidate=local.replace(hour=hour,minute=minute,second=0,microsecond=0)+timedelta(days=(settings['weekday']-local.isoweekday())%7)
        if candidate<=local:candidate+=timedelta(days=7)
        return candidate.astimezone(timezone.utc).isoformat()

    def read(self,account):
        scope=self.analysis.scope(account)
        row=self.p.repo.read(scope,'artifact',KEY)
        if row:return row['value']
        now=self.clock()
        settings={'kind':KEY,'enabled':True,'automaticExternalDispatch':False,'periodDays':7,'weekday':1,'time':'09:00','timezone':'Asia/Shanghai',
            'revision':1,'options':{'days':7,'category':'all','includeNotes':True,**source_options({})},'initializedAt':now.isoformat()}
        settings['nextDueAt']=self.next_due(now,settings)
        with self.p.db.transaction():
            row=self.p.repo.read(scope,'artifact',KEY)
            if row:return row['value']
            self.p.repo.put(scope,'artifact',KEY,settings,0)
        return settings

    def update(self,account,data):
        scope=self.analysis.scope(account);key='schedule-operation-'+digest(identifier(data.get('operationId')))[:40]
        signature=digest(data)
        with self.p.db.transaction():
            prior=self.p.repo.read(scope,'artifact',key)
            if prior:
                require(prior['value']['signature']==signature,'IDEMPOTENCY_CONFLICT');return prior['value']['settings']
            current=copy.deepcopy(self.read(account))
            require(type(data.get('expectedRevision')) is int and data['expectedRevision']==current['revision'],'SCHEDULE_REVISION_CONFLICT')
            require(data.get('automaticExternalDispatch') is None or type(data.get('automaticExternalDispatch')) is bool,'INVALID_SCHEDULE')
            if data.get('automaticExternalDispatch') is True and not current.get('automaticExternalDispatch'):
                require(data.get('confirmedExternalDispatch') is True,'AUTOMATIC_ANALYSIS_AUTHORIZATION_REQUIRED')
                current['externalDispatchConsentAt']=self.clock().isoformat()
            for field in ('enabled','automaticExternalDispatch','periodDays','weekday','time','timezone'):
                if field in data:current[field]=data[field]
            require(type(current['enabled']) is bool and type(current['periodDays']) is int and 1<=current['periodDays']<=90,'INVALID_SCHEDULE')
            require(type(current['weekday']) is int and 1<=current['weekday']<=7,'INVALID_SCHEDULE')
            import re
            require(isinstance(current['time'],str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',current['time']),'INVALID_SCHEDULE')
            require(current['timezone'] in ('Asia/Shanghai','UTC'),'INVALID_SCHEDULE')
            if 'options' in data:
                from backend.agent.practice_analysis import filters
                require(isinstance(data['options'],dict),'INVALID_ANALYSIS_RANGE')
                current['options']={**filters(data['options']),**source_options(data['options'])}
            current['revision']+=1;current['updatedAt']=self.clock().isoformat();current['nextDueAt']=self.next_due(self.clock(),current)
            if current['periodDays']!=7:current['nextDueAt']=(self.clock()+timedelta(days=current['periodDays'])).isoformat()
            row=self.p.repo.read(scope,'artifact',KEY);self.p.repo.put(scope,'artifact',KEY,current,row['version'])
            self.p.repo.put(scope,'artifact',key,{'kind':'schedule-operation','signature':signature,'settings':current},0)
            return current

    def listing(self,account):
        return sorted((r for r in self.p.repo.all(self.analysis.scope(account),'artifact') if r.get('kind')=='analysis-candidate'),key=lambda r:r.get('createdAt',''),reverse=True)[:20]

    def tick(self,account):
        with self.p.db.transaction():
            settings=copy.deepcopy(self.read(account));now=self.clock()
            if not settings['enabled'] or datetime.fromisoformat(settings['nextDueAt'])>now:return {'status':'not-due'}
            scope=self.analysis.scope(account)
            prior_cutoff=datetime.fromisoformat(settings.get('lastCapturedAt',settings['initializedAt']))
            request=copy.deepcopy(settings['options']);request['days']=0
            snapshot=self.analysis.capture(account,request,now)
            fingerprint=content_fingerprint(snapshot)
            outcome={'status':'skipped-no-new-records'}
            if fingerprint!=settings.get('lastFingerprint') and (snapshot['stats']['practicedQuestions']>0 or snapshot['hasNonPracticeActivity']):
                # Detect changes over full history, then freeze only the missed
                # interval. Static catalog changes alone must not trigger calls.
                snapshot=self.analysis.capture(account,request,now,window_start=prior_cutoff)
                if not (snapshot['stats']['practicedQuestions']>0 or snapshot['hasNonPracticeActivity']):
                    row=self.p.repo.read(scope,'artifact',KEY)
                    settings.update(lastFingerprint=fingerprint,lastCapturedAt=now.isoformat(),lastOutcome={'status':'skipped-no-new-records'},
                        nextDueAt=self.next_due(now,settings) if settings['periodDays']==7 else (now+timedelta(days=settings['periodDays'])).isoformat())
                    self.p.repo.put(scope,'artifact',KEY,settings,row['version'])
                    return {'status':'skipped-no-new-records'}
                window={'from':prior_cutoff.isoformat(),'through':now.isoformat(),'scheduledFor':settings['nextDueAt'],
                    'missedMerged':now-datetime.fromisoformat(settings['nextDueAt'])>=timedelta(days=settings['periodDays'])}
                snapshot['scheduleWindow']=window
                candidate_id='analysis-candidate-'+fingerprint[:40]
                if not self.p.repo.read(scope,'artifact',candidate_id):
                    self.p.repo.put(scope,'artifact',candidate_id,{'id':candidate_id,'kind':'analysis-candidate','status':'awaiting-manual-analysis',
                        'snapshot':snapshot,'fingerprint':fingerprint,'window':window,'createdAt':now.isoformat()},0)
                outcome={'status':'awaiting-manual-analysis','candidateId':candidate_id,'window':window}
                if settings.get('automaticExternalDispatch') and settings.get('externalDispatchConsentAt'):
                    if not self.analysis.config.api_key:return {'status':'unavailable'}
                    try:
                        job=self.analysis.submit(account,{**request,'idempotencyKey':'auto-analysis-'+fingerprint[:48]},captured=snapshot)
                    except AppError as error:
                        if error.code=='ANALYSIS_BUSY':return {'status':'busy'}
                        raise
                    row=self.p.repo.read(scope,'artifact',candidate_id);candidate=row['value']
                    candidate.update(status='submitted',jobId=job['id'])
                    self.p.repo.put(scope,'artifact',candidate_id,candidate,row['version'])
                    outcome={'status':'submitted','jobId':job['id'],'candidateId':candidate_id,'window':window}
            settings.update(lastFingerprint=fingerprint,lastCapturedAt=now.isoformat(),lastOutcome=outcome,
                nextDueAt=self.next_due(now,settings) if settings['periodDays']==7 else (now+timedelta(days=settings['periodDays'])).isoformat())
            row=self.p.repo.read(scope,'artifact',KEY);self.p.repo.put(scope,'artifact',KEY,settings,row['version'])
            return outcome

    async def loop(self):
        while True:
            rows=self.p.db.all("SELECT DISTINCT user_id FROM entities WHERE course_id='practice-global' AND kind='artifact' AND id=? AND deleted=0",(KEY,))
            for row in rows:
                if row['user_id'].startswith('practice:'):
                    try:self.tick(row['user_id'][9:])
                    except (AppError,ValueError):pass
            await asyncio.sleep(30)

    def start(self):
        if self.runner is None:self.runner=asyncio.create_task(self.loop())

    async def stop(self):
        if self.runner:
            self.runner.cancel();await asyncio.gather(self.runner,return_exceptions=True);self.runner=None
