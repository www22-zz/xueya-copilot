"""Rebuild the fixed 408 bank solely from reviewed repository content.

Run: python -m scripts.build_exam408_bank [--check]. No network/model calls.
Historical concepts are clearly adapted; this does not reproduce exam papers.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from backend.agent.exam408_authored import CASES, COMPUTER_ORGANIZATION
from backend.agent.exam408_adapted import ROWS
from backend.agent.exam408_cases import CASES as HISTORICAL_CASES
from backend.agent.exam408_topics import classify, order
from backend.agent.data_structure_code import EXERCISES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'backend/xueya/data'
OUTPUT = DATA/'exam408_bank.json'
SUBJECTS = {'ds':'数据结构','co':'计算机组成原理','os':'操作系统','cn':'计算机网络'}
SOURCE_INDEX = 'https://www.xit.edu.cn/yjsfk/kyzykwtkw/list.htm'


def base(identifier, subject, topic, kind, prompt, title, origin):
    return {'id':identifier,'category':'exam408','bankSource':'exam408','subject':subject,
            'topic':topic,'tags':[topic],'type':kind,'difficulty':'中等','prompt':prompt,
            'title':title,'origin':origin}


def adapted_singles():
    metadata=json.loads((DATA/'exam408_selection.json').read_text(encoding='utf-8'))['selected']
    rows={}
    for row in ROWS.splitlines():
        if not row.strip():continue
        identifier,prompt,options,answer,explanation=row.strip().split('|')
        assert identifier not in rows, identifier
        rows[identifier]=(prompt,options.split('~'),int(answer),explanation)
    assert set(rows)=={q['id'] for q in metadata}
    result=[]
    for q in metadata:
        prompt,options,answer,explanation=rows[q['id']]
        item=base(q['id'],q['subject'],q['topic'],'single',prompt,
                  f"{q['year']} 考点改编 · {q['topic']}",
                  {'kind':'adapted','label':'历年考点改编（非原题）','year':q['year'],'number':q['originalNumber']})
        item.update(year=q['year'],originalNumber=q['originalNumber'],tags=q['tags'],
                    options=options,answer=answer,explanation=explanation,
                    references=[{**ref,'label':'原卷考点参考（非本题答案）' if i==0 else '原卷解析参考（非本题答案）' if i==1 else '原题索引参考'} for i,ref in enumerate(q['references'])])
        result.append(item)
    return result


def authored_singles(count):
    curriculum=json.loads((DATA/'data_structures_practice.json').read_text(encoding='utf-8'))['questions']
    fixed=json.loads((DATA/'practice_bank.json').read_text(encoding='utf-8'))['questions']
    existing=[q for q in curriculum if q['type']=='single'][:50]
    existing += [q for q in fixed if q['type']=='single' and q['subject'] in ('操作系统','计算机网络')]
    output=[]
    for q in existing:
        item=base('e408-original-'+q['id'], '数据结构' if q['subject']=='数据结构与算法' else q['subject'],
                  q.get('subtopic') or q.get('topic') or q['tags'][0],'single',q['prompt'],q['title'],
                  {'kind':'authored','label':'项目原创题选编','originalQuestionId':q['id']})
        item.update(options=q['options'],answer=q['answer'],explanation=q['explanation'])
        output.append(item)
    for i,line in enumerate(COMPUTER_ORGANIZATION.strip().splitlines(),1):
        topic,prompt,options,answer,explanation=line.split('|')
        item=base(f'e408-original-co-{i:02}','计算机组成原理',topic,'single',prompt,topic,
                  {'kind':'authored','label':'原创模拟题'})
        item.update(options=options.split('~'),answer=int(answer),explanation=explanation)
        output.append(item)
    if len(output)!=count:
        raise ValueError(f'Explicit authored pool has {len(output)} questions; expected {count}, no padding permitted')
    return output


def adapted_composites():
    sources=json.loads((DATA/'exam408_sources.json').read_text(encoding='utf-8'))
    result=[]
    for identifier,topic,prompt,parts in HISTORICAL_CASES:
        _,year,number=identifier.split('-');year=int(year);number=int(number)
        subject=SUBJECTS['ds' if number<43 else 'co' if number<45 else 'os' if number<47 else 'cn']
        item=base(identifier,subject,topic,'short',prompt,f'{year} 考点改编 · {topic}',
                  {'kind':'adapted','label':'历年综合考点改编（非原题）','year':year,'number':number})
        item.update(year=year,originalNumber=number,
            parts=[{'id':f'p{i+1}','label':label,'points':points,'reference':reference} for i,(label,points,reference) in enumerate(parts)],
            answer='对照各小问独立编写的参考解答自评',keyPoints=[],followUps=[],
            explanation='本题参考对应年份考点重新编写，条件、数据和小问均以本页为准。分值为练习建议，不是原卷官方分值；原卷链接只用于追溯考点，不是本题答案。',
            references=[{'label':'原卷考点参考（非本题答案）','url':sources[str(year)]['paper'],'question':number},
                        {'label':'原卷解析参考（非本题答案）','url':sources[str(year)]['answers'],'question':number}])
        result.append(item)
    return result


def authored_composites():
    result=[]
    for name,q in EXERCISES.items():
        item=base('e408-original-algorithm-'+name,'数据结构',q['tag'],'short',q['prompt'],q['title'],
                  {'kind':'authored','label':'项目原创算法综合题'})
        item.update(parts=[{'id':'p1','label':'算法思路','points':4,'reference':q['explanation']},
                           {'id':'p2','label':'算法实现','points':8,'reference':q['c']},
                           {'id':'p3','label':'复杂度分析','points':4,'reference':f"时间复杂度{q['time']}，空间复杂度{q['space']}。应同时说明循环或递归和辅助结构的来源。"}],
                    answer=q['explanation'],keyPoints=[],followUps=[],explanation='先独立作答，再对照参考算法与分析自评；不进行在线代码判题。')
        result.append(item)
    for i,(subject,topic,title,prompt,parts) in enumerate(CASES,1):
        item=base(f'e408-original-case-{i:02}',SUBJECTS[subject],topic,'short',prompt,title,
                  {'kind':'authored','label':'原创模拟综合题'})
        item.update(parts=[{'id':f'p{n+1}','label':label,'points':points,'reference':reference}
                           for n,(label,points,reference) in enumerate(parts)],
                    answer='对照各小问参考解答自评',keyPoints=[],followUps=[],explanation='本题为项目独立编写的模拟题，分值是本题自评建议，不冒充历年真题或官方评分。')
        result.append(item)
    return result


def build_bank():
    selected=adapted_singles()
    questions=selected+authored_singles(240-len(selected))+authored_composites()+adapted_composites()
    assert len(questions)==300 and len({q['id'] for q in questions})==300
    assert len({re.sub(r'\s+','',q['prompt']) for q in questions})==300
    for q in questions:classify(q)
    questions.sort(key=order)
    for i,q in enumerate(questions,1):
        q['number']=i
    payload=json.dumps(questions,ensure_ascii=False,sort_keys=True).encode()
    return {'version':'exam408-20261029-'+hashlib.sha256(payload).hexdigest()[:16],
            'name':'408考研题库','indexReference':SOURCE_INDEX,
            'sourcePolicy':'151道历年考点改编、149道项目原创；不是300道逐字原卷真题。改编题条件和答案以本页独立版本为准。',
            'questions':questions}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    value=build_bank()
    if args.check:
        assert json.loads(OUTPUT.read_text(encoding='utf-8'))==value,'Bank differs from reviewed source content; rebuild first'
        from backend.xueya.practice_catalog import exam_bank
        exam_bank()
    else:
        OUTPUT.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'questions':len(value['questions']),
        'types':dict(Counter(q['type'] for q in value['questions'])),
        'origins':dict(Counter(q['origin']['kind'] for q in value['questions'])),
        'sourceReadingRequired':sum(bool(q.get('paper')) for q in value['questions'])},ensure_ascii=False))


if __name__=='__main__':main()
