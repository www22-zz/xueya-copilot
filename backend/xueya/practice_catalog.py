"""Independent practice sources, with legacy questions retained for history."""
import copy
import json
from functools import lru_cache
from pathlib import Path

from .common import digest, require
from .practice_bank import bank

EXAM_FILE = Path(__file__).with_name('data')/'exam408_bank.json'


@lru_cache(maxsize=1)
def exam_bank():
    value = json.loads(EXAM_FILE.read_text(encoding='utf-8'))
    questions = value['questions']
    require(len(questions) == 300 and len({q['id'] for q in questions}) == 300, 'INVALID_EXAM_BANK')
    require(sum(q['type'] == 'single' for q in questions) == 240, 'INVALID_EXAM_COUNTS')
    require(sum(q['type'] == 'short' for q in questions) == 60, 'INVALID_EXAM_COUNTS')
    for q in questions:
        require(q['category'] == 'exam408' and q['bankSource'] == 'exam408'
                and q.get('tags') and q.get('subject') and q.get('topic'), 'INVALID_EXAM_QUESTION')
        if q['type'] == 'single':
            require(len(q['options']) == 4 and type(q['answer']) is int and 0 <= q['answer'] < 4, 'INVALID_EXAM_ANSWER')
        else:
            parts = q.get('parts') or []
            require(parts and len({p['id'] for p in parts}) == len(parts)
                    and all(p['points'] > 0 and p['reference'] for p in parts), 'INVALID_EXAM_PARTS')
    return value


def workspace_catalog(generation, account):
    fixed = [dict(copy.deepcopy(q), bankSource='algorithm' if q['category'] == 'hot100' else 'legacy')
             for q in bank()['questions']]
    historical = generation.catalog(account, history=True)['questions']
    known = {q['id'] for q in fixed}
    fixed.extend(dict(copy.deepcopy(q), bankSource='legacy') for q in historical if q['id'] not in known)
    exam = exam_bank()
    return {'version':'practice-workspace-'+digest([bank()['version'],exam['version'],[q['id'] for q in fixed]])[:24],
            'questions':fixed+exam['questions'], 'generations':[], 'available':True,
            'sources':[{'id':'algorithm','name':'力扣算法 Hot100','count':100},
                       {'id':'materials','name':'资料练习100题','count':0,'status':'preparing'},
                       {'id':'exam408','name':'408考研题库','count':300}]}


def exam_question(question_id):
    return next((q for q in exam_bank()['questions'] if q['id'] == question_id),None)
