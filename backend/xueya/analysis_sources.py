"""Immutable evidence projection for multi-source learning reports, no RAG reads."""
import copy
import json
import re
from datetime import datetime, timezone

from backend.agent.practice_analysis import instant
from .account_scope import account_owner
from .common import digest, dumps, identifier, require
from .study_space_service import StudySpaceService

SOURCES=('conversations','courses','quizzes','plans')


def source_options(value):
    result={}
    for key in SOURCES:
        setting=value.get('include'+key.title(),True)
        require(type(setting) is bool,'INVALID_ANALYSIS_RANGE')
        result['include'+key.title()]=setting
    for key in ('excludedSessionIds','includedSessionIds'):
        ids=value.get(key,[])
        require(isinstance(ids,list) and len(ids)<=200,'INVALID_ANALYSIS_RANGE')
        result[key]=sorted({identifier(i) for i in ids})
    return result


def workspace_owner(platform,account):
    if account=='local':return 'local-user'
    rows=platform.db.all("SELECT value FROM meta WHERE key='local-account-v1' OR key LIKE 'account-v2:%'")
    for row in rows:
        value=json.loads(row['value'])
        if (value.get('learningOwner') or value.get('username'))==account:
            return account_owner(value)
    return None


def sessions(platform,account):
    owner=workspace_owner(platform,account)
    stored=platform.repo.get_workspace(owner) if owner else None
    result=[]
    for course in (stored or {}).get('data',{}).get('courses',[]):
        data=course.get('data',{})
        for session in data.get('sessions',[]):
            if not isinstance(session,dict) or not isinstance(session.get('id'),str):continue
            messages=data.get('messages',[]) if session['id']==data.get('sessionId') else session.get('messages',[])
            title=str(session.get('title','未命名对话'))[:100]
            learning=bool(re.search(r'学习|复习|算法|数据结构|计算机|进程|线程|网络|缓存|函数|编程|复杂度|栈|队列|二叉树|考研|数学|英语|物理|知识|题目',title+' '+ ' '.join(str(m.get('text',''))[:500] for m in messages if isinstance(m,dict) and m.get('role')=='user')))
            result.append({'id':session['id'],'courseId':course['id'],'title':title,'learningRelated':learning,
                'updatedAt':session.get('updatedAt') or session.get('createdAt'),'messages':messages})
    return result


def enrich(platform,account,snapshot,options):
    snapshot=copy.deepcopy(snapshot)
    cutoff=instant(snapshot['cutoff']);start=instant(snapshot.get('start'))
    def included(at):
        time=instant(at)
        return time is not None and time<=cutoff and (start is None or time>=start)
    evidence=[];counts={'conversations':0,'userQuestions':0,'courseConfirmations':0,'courseUndone':0,'planOperations':0,
        'quizAttempts':0,'objective':0,'objectiveCorrect':0,'aiReference':0,'humanCorrection':0,'ungraded':0,'disputed':0}
    seen_messages=set();truncated=False
    if options['includeConversations']:
        for session in sessions(platform,account):
            if session['id'] in options['excludedSessionIds'] or not (session['learningRelated'] or session['id'] in options['includedSessionIds']):continue
            excerpts=[]
            for index,message in enumerate(session['messages']):
                if not isinstance(message,dict) or message.get('role')!='user':continue
                # Missing historical timestamps are excluded, never assigned a made-up date.
                at=message.get('createdAt') or message.get('at')
                if not at and index+1<len(session['messages']):at=session['messages'][index+1].get('createdAt')
                identity=message.get('id') or digest([message.get('text'),at])
                if identity in seen_messages or not included(at):continue
                seen_messages.add(identity);counts['userQuestions']+=1
                excerpts.append({'messageId':identity,'at':at,'text':str(message.get('text',''))[:800]})
            if excerpts:
                counts['conversations']+=1
                evidence.append({'id':'session:'+session['id'],'type':'conversation','sessionId':session['id'],
                    'title':session['title'],'courseId':session['courseId'],'excerpts':excerpts[-8:]})
                truncated|=len(excerpts)>8
    service=StudySpaceService(platform);scope=service._scope(account)
    for event in platform.repo.all(scope,'event'):
        if not included(event.get('at')):continue
        if event.get('source')=='course' and options['includeCourses']:
            counts['courseConfirmations' if event.get('completed') else 'courseUndone']+=1
            evidence.append({'id':'event:'+event['id'],'type':'course','title':'手动课程完成状态',
                **{k:event.get(k) for k in ('courseId','episodeId','completed','completionSource','at')}})
        elif event.get('source')=='plan' and options['includePlans']:
            counts['planOperations']+=1
            evidence.append({'id':'event:'+event['id'],'type':'plan','title':'计划执行操作',
                **{k:event.get(k) for k in ('planId','taskId','action','at')}})
    if options['includeQuizzes']:
        from .space_quiz import SpaceQuiz
        for row in platform.repo.all(scope,'attempt'):
            attempt=SpaceQuiz.normalize(row)
            if not included(attempt.get('createdAt')) and not any(included(e.get('completedAt') or e.get('createdAt')) for e in attempt.get('evaluations',[])):continue
            counts['quizAttempts']+=1
            effective=attempt.get('effectiveEvaluation') or {}
            source=effective.get('source');result=effective.get('result') or {}
            if effective.get('status')=='disputed':counts['disputed']+=1
            elif effective.get('status')!='graded':counts['ungraded']+=1
            elif source in ('objective','objective-recheck'):
                counts['objective']+=1;counts['objectiveCorrect']+=result.get('correct') is True
            elif source=='human':counts['humanCorrection']+=1
            elif source in ('ai-reference','ai-review'):counts['aiReference']+=1
            else:counts['ungraded']+=1
            evidence.append({'id':'attempt:'+attempt['id'],'type':'quiz','title':str(attempt.get('questionSnapshot',{}).get('prompt') or '历史作答')[:200],
                'attemptId':attempt['id'],'questionId':attempt.get('questionId'),'at':attempt.get('createdAt'),
                'answerExcerpt':str(attempt.get('answer',''))[:800], 'evaluation':copy.deepcopy(effective),
                'url':'#space/practice/ai/'+str(attempt.get('questionId'))+'/'+attempt['id']})
    evidence.sort(key=lambda item:item.get('at') or (item.get('excerpts') or [{}])[-1].get('at',''))
    if len(evidence)>150:truncated=True;evidence=evidence[-150:]
    extra={'counts':counts,'evidence':evidence,'options':options,'truncated':truncated}
    # Keep complete program counts, trim only explanatory material at a visible boundary.
    while len(dumps(extra).encode())>60000 and evidence:
        evidence.pop(0);truncated=True;extra['truncated']=True
    snapshot['activitySources']=extra
    snapshot['hasNonPracticeActivity']=bool(any(counts.values()))
    if snapshot['stats']['practicedQuestions']==0 and snapshot['hasNonPracticeActivity']:
        snapshot['omittedUnpracticedQuestions']=len(snapshot['questions'])
        snapshot['questions']=[]
        snapshot['limitations'].append('没有固定题练习记录，本次只发送真实活动依据和题库总量；未作答固定题不作为能力证据或建议引用。')
    snapshot['limitations']+=['对话仅据用户提问推断关注点，不把AI解释或看过课程视为掌握。历史缺日期消息不纳入时间统计；分支共享消息按ID去重。',
        '课程确认、计划操作分开列示，不相加为学习次数；观看时长不由完成状态推测。小测评阅版本不增加作答次数，AI参考分、人工修正和客观判分分开。']
    if truncated:snapshot['limitations'].append('多来源细节达到范围上限，已保留最近依据；程序统计保留完整，摘录不代表全部记录。')
    while len(dumps(snapshot).encode())>120000 and evidence:
        evidence.pop(0);extra['truncated']=True
    require(len(dumps(snapshot).encode())<=122000,'ANALYSIS_TOO_LARGE')
    return snapshot


def content_fingerprint(snapshot):
    value=copy.deepcopy(snapshot)
    for key in ('cutoff','start','previousPeriod','serverSeq','scheduleWindow'):value.pop(key,None)
    return digest(value,canonical=True)
