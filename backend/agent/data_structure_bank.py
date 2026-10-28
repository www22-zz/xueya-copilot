"""Build the explicit 100+100 data-structure curriculum from authored and selected content."""
import copy
import json
from pathlib import Path
import re

from backend.agent.assessment import validate_question
from backend.agent.data_structure_code import EXERCISES
from backend.agent.data_structure_curriculum import UNITS
from backend.xueya.common import digest, require

PACKAGE_ID = 'data-structures-curated-20261028-v1'
TEXTBOOK_HASH = '536aca02ecdab9352293b3cdcc1ac760e2e6dcdf5a581f03f0b71eeda1047757'
ROOT = Path(__file__).resolve().parents[2]
PACKAGE_FILE = ROOT / 'backend/xueya/data/data_structures_practice.json'


def textbook_pages(text):
    parts = re.split(r'^## PDF 第 (\d+) 页\s*$', text, flags=re.M)
    return {int(parts[i]): parts[i+1].strip() for i in range(1, len(parts), 2)}


def background(pages, terms, subtopic):
    """A real textbook excerpt for the knowledge point; never claim this is the original problem."""
    candidates = []
    specific = [t for t in re.split(r'[、与及\s]+', subtopic) if len(t) >= 2]
    for number, text in pages.items():
        if number < 18 or number > 300:
            continue  # skip contents, publisher pages and appendices
        primary = sum(text.count(term) for term in terms)
        if not primary:
            continue
        score = primary + sum(5*text.count(term) for term in specific)
        candidates.append((score, -number, number, text))
    require(candidates, 'CURATED_NO_TEXTBOOK_REFERENCE')
    _, _, page, text = max(candidates)
    term = next((term for term in specific + terms if term in text), terms[0])
    start = max(0, text.find(term)-40)
    return {'kind': 'textbook-background', 'fileHash': TEXTBOOK_HASH, 'page': page,
            'quote': text[start:start+240], 'relation': '相关知识点背景，不代表教材收录了此原题或完整题解'}


def parse_row(row):
    kind, title, prompt, options, answer, explanation, tag = [part.strip() for part in row.split('|')]
    q = {'type': {'S':'single', 'M':'multiple', 'F':'fill'}[kind], 'title': title,
         'prompt': prompt, 'explanation': explanation, 'subtopic': tag}
    if kind in ('S', 'M'):
        q['options'] = options.split('~')
        q['answer'] = int(answer) if kind == 'S' else [int(i) for i in answer.split(',')]
    else:
        aliases = answer.replace('\x00', '\\0').split('~')
        q.update(answer=aliases[0], acceptedAnswers=aliases, answers=[aliases])
    q['origin'] = {'kind':'authored', 'label':'新编练习'}
    return q


def code_question(slug):
    item = EXERCISES[slug]
    return {'type':'code', 'title':item['title'], 'prompt':item['prompt'], 'explanation':item['explanation'],
            'subtopic':item['tag'], 'solutions':{'c':item['c'], 'python':item['py']},
            'samples':[{'input':json.dumps(a, ensure_ascii=False), 'output':json.dumps(b, ensure_ascii=False)} for a,b in item['tests']],
            'complexity':{'time':item['time'], 'space':item['space']},
            'pitfalls':'先处理空输入、下标和指针边界；参考代码中的参数约定与样例表示方式见题干。',
            'origin':{'kind':'authored','label':'新编基础代码题'}}


def validate_package(package):
    require(package.get('id') == PACKAGE_ID and len(package.get('questions', [])) == 200, 'CURATED_INVALID_PACKAGE')
    questions = package['questions']
    if package.get('contentHash'):
        content = {k:v for k,v in package.items() if k != 'contentHash'}
        require(package['contentHash'] == digest(content, canonical=True), 'CURATED_CONTENT_CHANGED')
    require(len({q['id'] for q in questions}) == 200, 'CURATED_DUPLICATE_ID')
    require(len({re.sub(r'\s+', '', q['prompt']) for q in questions}) == 200, 'CURATED_DUPLICATE_PROMPT')
    for category in ('hot100','basic'):
        subset = [q for q in questions if q['category'] == category]
        require(len(subset) == 100, 'CURATED_INVALID_COUNTS')
        require({q['type'] for q in subset} == {'single','multiple','fill','code'}, 'CURATED_INVALID_TYPES')
        for _, unit, *_ in UNITS:
            require(sum(q['topic'] == unit for q in subset) == 10, 'CURATED_INVALID_COVERAGE')
    for q in questions:
        require(q.get('subtopic') and q['subtopic'] in q['tags'], 'CURATED_MISSING_SUBTOPIC')
        require(q.get('origin', {}).get('kind') in ('authored','selected'), 'CURATED_MISSING_ORIGIN')
        ref = q['references'][0]
        require(ref.get('fileHash') == TEXTBOOK_HASH and ref.get('quote') and type(ref.get('page')) is int, 'CURATED_INVALID_REFERENCE')
        sources = [{'id':q['sourceId'], 'courseId':q['courseId'], 'version':q['sourceVersion'], 'quote':q['evidenceQuote']}]
        validate_question(q, sources)
        if q['type'] == 'multiple':
            require(len(q['answer']) >= 2, 'CURATED_INVALID_MULTIPLE')
    return package


def build(root=ROOT):
    root = Path(root)
    existing = json.loads((root/'backend/xueya/data/practice_bank.json').read_text(encoding='utf-8'))['questions']
    old = {q['id']:q for q in existing}
    pages = textbook_pages((root/'materials/data-structures-textbook/textbook-ocr.md').read_text(encoding='utf-8'))
    questions = []
    for category in ('hot100','basic'):
        for unit_index, (slug, title, terms, hot, basic, selected) in enumerate(UNITS):
            authored = [parse_row(line) for line in (hot if category == 'hot100' else basic).strip().splitlines()]
            if category == 'hot100':
                for old_id in selected:
                    q = copy.deepcopy(old[old_id])
                    q.update(subtopic=q['tags'][0], origin={'kind':'selected','label':'已有经典题选编',
                        'originalQuestionId':old_id, 'url':q.get('leetcodeUrl'), 'source':'项目已有官方Hot100题单'})
                    authored.append(q)
            else:
                authored.append(code_question(slug))
            require(len(authored) == 10, 'CURATED_INVALID_UNIT')
            for i, q in enumerate(authored):
                ref = background(pages, terms, q['subtopic'])
                q.update(id=f'ds-{category}-{slug}-{i+1:02d}', category=category, subject='数据结构与算法',
                    topic=title, tags=list(dict.fromkeys([title, q['subtopic'], *q.get('tags', [])]))[:5],
                    curated=True, generated=False, number=unit_index*10+i+1, unitOrder=unit_index,
                    courseId='data-structures', version='1', sourceId='textbook-page-'+str(ref['page']),
                    sourceVersion=TEXTBOOK_HASH, documentName='数据结构—从概念到C++实现（第3版）.pdf',
                    evidenceQuote=ref['quote'], references=[ref],
                    quality={'provenance':'textbook-background-linked','answerSupport':'reference-solution',
                             'review':{'method':'authored-and-structural-checks','independentHumanReview':False}})
                if category == 'basic':
                    q['difficulty'] = '基础'
                else:
                    q['difficulty'] = q.get('difficulty', '中等')
                questions.append(q)
    package = {'id':PACKAGE_ID, 'version':PACKAGE_ID, 'name':'数据结构·经典Hot 100与基础100',
        'subject':'数据结构与算法', 'textbookHash':TEXTBOOK_HASH,
        'description':'Hot覆盖经典重点、易错辨析与经典算法；基础覆盖概念、直接应用与小型代码练习。热门指经典选题，不代表实时热度统计。',
        'units':[{'id':slug, 'name':title, 'hot100':10, 'basic':10} for slug,title,*_ in UNITS],
        'questions':questions}
    validate_package(package)
    package['contentHash'] = digest(package, canonical=True)
    return package


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=PACKAGE_FILE)
    args = parser.parse_args()
    package = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(package, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'id':package['id'], 'questions':len(package['questions']), 'units':len(package['units']),
                      'contentHash':package['contentHash']}, ensure_ascii=False))
