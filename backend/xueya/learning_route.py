"""Persisted phase routes and exercise-bound completion, using platform records."""
import copy
from .common import digest, require, utc_now


def build(service, account, plan):
    scope = service._scope(account)
    questions = service.repo.all(scope, 'question')
    materials=getattr(service.platform,'material_learning',None)
    accessible=None
    if materials:
        accessible=materials.accessible_concepts(account)
    difficulty = {'基础':'简单', '进阶':'中等', '挑战':'困难'}.get(plan.get('difficulty'), plan.get('difficulty','简单'))
    phases = {}
    used = set()
    for day in plan['days']:
        for task in day['tasks']:
            label = task.get('phase', '学习与巩固')
            phase = phases.setdefault(label, {'id':'phase-'+digest(label)[:20], 'title':label, 'stages':[],
                'reason':plan.get('explanation','按计划任务顺序学习'), 'startDate':day['date'], 'endDate':day['date']})
            phase['endDate'] = day['date']
            source_id = task.get('sourceTaskId', task['id'])
            stage = next((s for s in phase['stages'] if s['id'] == source_id), None)
            if stage is None:
                stage = {'id':source_id, 'title':task['title'], 'nodes':[], 'prerequisites':task.get('dependsOn',[]),
                         'reason':'按计划中的先修任务和每日时间预算安排', 'startDate':day['date'], 'endDate':day['date']}
                phase['stages'].append(stage)
            stage['endDate'] = day['date']
            resource = task.get('resource') or {}
            concept_id = resource.get('conceptId')
            material = service.repo.read(scope, 'artifact', resource.get('materialId','')) if resource.get('materialId') else None
            concept = next((n for n in (material or {}).get('value',{}).get('concepts',[]) if n['id'] == concept_id), None)
            if accessible is not None and concept_id not in accessible:concept=None
            wanted = max(1, (task['minutes']+9)//10)
            eligible = sorted((q for q in questions if concept and q['id'] in concept['questionIds']
                               and q.get('conceptId') == concept_id and q.get('difficulty') == difficulty and q['id'] not in used), key=lambda q:q['id'])
            chosen = eligible[:wanted]; used.update(q['id'] for q in chosen)
            refs = [{'id':q['id'],'revision':q['version'],'sourceRevision':q.get('sourceRevision')} for q in chosen]
            stage['nodes'].append({'id':task['id'], 'conceptId':concept_id, 'materialId':resource.get('materialId'),
                'title':concept['label'] if concept else task['title'], 'description':concept.get('description','') if concept else '',
                'date':day['date'], 'minutes':task['minutes'], 'difficulty':difficulty, 'questions':refs,
                'requiredCount':wanted, 'missingCount':wanted-len(refs), 'video':task.get('video'),
                'readiness':'ready' if len(refs)==wanted else 'questions-needed' if concept else 'materials-needed'})
    return {'version':1, 'createdAt':utc_now(), 'phases':list(phases.values()),
            'selectionRule':'每题预留10分钟；按所选难度绑定题目版本；不足时保留缺口，不跨难度替代。',
            'unallocatedTasks':len(plan.get('remaining',[]))}


def nodes(route):
    return [n for p in route['phases'] for s in p['stages'] for n in s['nodes']]


def validate_attempt(service, account, value, question):
    if not value.get('planId'):
        return {}
    row = service.repo.read(service._scope(account), 'plan', value['planId'])
    require(row and row['value'].get('status') == 'active', 'PLAN_NOT_ACTIVE')
    plan = row['value']
    node = next((n for n in nodes(plan.get('learningRoute',{'phases':[]})) if n['id'] == value.get('nodeId')), None)
    require(node and any(q['id']==question['id'] and q['revision']==question['revision'] for q in node['questions']), 'PLAN_QUESTION_MISMATCH')
    materials=getattr(service.platform,'material_learning',None)
    if materials:
        from .concept_practice import context
        owner=materials.account_owner_for(account)
        require(owner is not None,'CONCEPT_NOT_ACCESSIBLE')
        require(node['conceptId'] in materials.accessible_concepts(account),'CONCEPT_NOT_ACCESSIBLE')
    return {'planId':plan['id'], 'nodeId':node['id']}


def view(service, account, plan):
    route = copy.deepcopy(plan.get('learningRoute'))
    if not route:
        return None
    attempts = [a for a in service.repo.all(service._scope(account),'attempt') if a.get('planId') == plan['id']]
    for phase in route['phases']:
        first_results = []; report_attempts = []; attempted=0; correct=0; graded=0; repeats=0
        for stage in phase['stages']:
            for node in stage['nodes']:
                valid = []
                for ref in node['questions']:
                    rows = sorted((a for a in attempts if a.get('nodeId')==node['id'] and a['questionId']==ref['id']
                                   and a['questionRevision']==ref['revision']), key=lambda a:(a['createdAt'],a['id']))
                    if rows:
                        valid.append(ref['id']); attempted+=1; repeats+=len(rows)-1
                        # First attempt's original evaluation, never later regrades.
                        evaluation = (rows[0].get('evaluations') or [{}])[0]
                        result = evaluation.get('result') or {}
                        known = evaluation.get('status')=='graded' and type(result.get('correct')) is bool and rows[0].get('effectiveEvaluation',{}).get('status')!='disputed'
                        graded+=int(known); correct+=int(known and result['correct'])
                        first_results.append(known)
                        report_attempts.append({'questionId':ref['id'], 'attemptId':rows[0]['id'],
                            'correct':result.get('correct') if known else None, 'repeats':len(rows)-1,
                            'nodeId':node['id'], 'title':node['title']})
                node['submittedCount']=len(valid)
                node['completed']=node['readiness']=='ready' and len(valid)==len(node['questions']) and bool(valid)
            stage['completed']=bool(stage['nodes']) and all(n['completed'] for n in stage['nodes'])
            stage['minutes']=sum(n['minutes'] for n in stage['nodes'])
            stage['questionCount']=sum(len(n['questions']) for n in stage['nodes'])
        phase['completed']=bool(phase['stages']) and all(s['completed'] for s in phase['stages'])
        phase['report']={'attemptedQuestions':attempted, 'gradedQuestions':graded, 'pendingQuestions':attempted-graded,
                         'firstCorrect':correct, 'firstAccuracy':correct/graded if graded else None,
                         'repeatAttempts':repeats, 'attempts':report_attempts,
                         'advice':'先复习本阶段首次答错的知识点，再进入下一阶段。' if correct<graded else '继续下一阶段，并安排间隔复习。' if graded else '依据不足，完成练习后再查看。'}
    route['days'] = []
    for day in plan['days']:
        items=[n for n in nodes(route) if n['date']==day['date']]
        route['days'].append({'date':day['date'],'isRestDay':day['isRestDay'],
            'completed':bool(items) and all(n['completed'] for n in items),
            'submittedCount':sum(n['submittedCount'] for n in items), 'requiredCount':sum(n['requiredCount'] for n in items)})
    return route


def sync_completion(service, account, plan_id):
    scope=service._scope(account)
    with service.platform.db.transaction():
        row=service.repo.read(scope,'plan',plan_id)
        if not row:return
        route=view(service,account,row['value'])
        if not route:return
        for day in route['days']:
            if day['completed']:
                key='study-completion-'+digest([plan_id,day['date']])[:40]
                if not service.repo.read(scope,'artifact',key):
                    service.repo.put(scope,'artifact',key,{'kind':'study-completion','planId':plan_id,
                        'date':day['date'],'createdAt':utc_now()},0)
