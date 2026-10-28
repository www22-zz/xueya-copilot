"""Content, C/Python reference examples, publication and non-destructive selection tests."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from backend.agent.data_structure_bank import build, validate_package, PACKAGE_FILE, TEXTBOOK_HASH, textbook_pages, ROOT
from backend.agent.data_structure_code import EXERCISES
from backend.xueya.app import create_app
from backend.xueya.config import Config
from backend.xueya.curated_practice import CuratedPractice
from backend.xueya.common import AppError


def test_real_curriculum_has_100_each_and_balanced_knowledge_units():
    package = json.loads(PACKAGE_FILE.read_text(encoding='utf-8'))
    assert build() == package
    validate_package(package)
    for category, expected in [('hot100',{'single':30,'multiple':20,'fill':30,'code':20}),
                               ('basic',{'single':40,'multiple':30,'fill':20,'code':10})]:
        rows = [q for q in package['questions'] if q['category'] == category]
        assert Counter(q['type'] for q in rows) == expected
        assert set(Counter(q['topic'] for q in rows).values()) == {10}
        assert [q['number'] for q in rows] == list(range(1,101))
        assert all(q['subject']=='数据结构与算法' and q['subtopic'] in q['tags'] for q in rows)
    assert Counter(q['origin']['kind'] for q in package['questions']) == {'authored':180,'selected':20}
    assert len({q['origin']['originalQuestionId'] for q in package['questions'] if q['origin']['kind']=='selected'}) == 20
    assert all(q['category'] != 'interview' for q in package['questions'])


def test_all_background_quotes_are_real_textbook_text_and_not_claimed_original_questions():
    pages = textbook_pages((ROOT/'materials/data-structures-textbook/textbook-ocr.md').read_text(encoding='utf-8'))
    package = json.loads(PACKAGE_FILE.read_text(encoding='utf-8'))
    for q in package['questions']:
        ref = q['references'][0]
        assert ref['quote'] in pages[ref['page']]
        assert ref['fileHash'] == TEXTBOOK_HASH
        assert '不代表' in ref['relation']
        if q['origin']['kind'] == 'selected':
            assert q['origin']['url'] == q['leetcodeUrl']


@pytest.mark.parametrize('slug', list(EXERCISES))
def test_authored_python_reference_examples(slug):
    item = EXERCISES[slug]
    namespace = {}
    exec(compile(item['py'], f'{slug}-reference', 'exec'), namespace)
    for value, expected in item['tests']:
        assert namespace['solve'](copy.deepcopy(value)) == expected


C_CHECKS = {
'complexity':'int a[]={1,-2,3}; if(sum_array(a,3)!=2 || sum_array(0,0)!=0) return 1;',
'linear':'Node b={2,0}, a={1,&b}; if(list_length(&a)!=2 || list_length(0)!=0) return 1;',
'stack':'if(!valid_parens("(())()") || valid_parens("())(") || !valid_parens("")) return 1;',
'strings':'int a[]={1,2,3,4}; reverse_array(a,4); if(a[0]!=4 || a[3]!=1) return 1; reverse_array(0,0);',
'trees':'TreeNode c={3,0,0}, b={2,&c,0}, a={1,&b,0}; if(tree_height(&a)!=3 || tree_height(0)!=0) return 1;',
'heap':'int a[]={1,3,2,7}, b[]={2,1}; if(!is_min_heap(a,4) || is_min_heap(b,2) || !is_min_heap(0,0)) return 1;',
'graphs':'const int a[100][100]={{0,1,1},{1,0,0},{1,0,0}}; if(vertex_degree(3,a,0)!=2 || vertex_degree(3,a,1)!=1) return 1;',
'search':'int a[]={1,3,5,8}; if(binary_search(a,4,5)!=2 || binary_search(a,4,4)!=-1 || binary_search(0,0,1)!=-1) return 1;',
'sorting':'int a[]={3,1,2,2}; insertion_sort(a,4); if(a[0]!=1 || a[1]!=2 || a[2]!=2 || a[3]!=3) return 1; insertion_sort(0,0);',
'design':'int a[]={1,1,2,2,3}; if(unique_sorted(a,5)!=3 || a[0]!=1 || a[1]!=2 || a[2]!=3 || unique_sorted(0,0)!=0) return 1;',
}


@pytest.mark.parametrize('slug', list(EXERCISES))
def test_authored_c_references_compile_and_run(slug, tmp_path):
    compiler = shutil.which('gcc') or shutil.which('clang')
    if not compiler:
        pytest.skip('C compiler unavailable; Python oracle remains separately tested')
    source = tmp_path/(slug+'.c')
    executable = tmp_path/(slug+'.exe')
    source.write_text(EXERCISES[slug]['c']+'\nint main(void) {\n'+C_CHECKS[slug]+'\nreturn 0;\n}\n', encoding='utf-8')
    result = subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror',str(source),'-o',str(executable)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert subprocess.run([str(executable)], timeout=5).returncode == 0


def seed_course(app):
    p = app.state.platform
    scope = p.scope('course-default')
    package = json.loads(PACKAGE_FILE.read_text(encoding='utf-8'))
    p.repo.put(scope, 'document', 'textbook-fixture', {'id':'textbook-fixture', 'name':'数据结构教材.pdf',
        'fileHash':TEXTBOOK_HASH, 'contentRevision':2, 'archived':False, 'superseded':False})
    sources = [{'id':'source-'+str(i), 'quote':q['evidenceQuote'], 'page':q['references'][0]['page'],
                'location':'第 '+str(q['references'][0]['page'])+' 页'} for i,q in enumerate(package['questions'])]
    service = CuratedPractice(p, SimpleNamespace(sources=lambda *args,**kwargs:sources))
    service.install(scope, package)
    return scope, service


def test_selection_publishes_200_preserves_progress_and_is_idempotent(tmp_path):
    app = create_app(Config(data_dir=tmp_path), start_jobs=False)
    with TestClient(app, base_url='http://localhost') as client:
        scope, service = seed_course(app)
        host = app.state.platform
        host.repo.put(scope,'note','private-note',{'text':'preserve me'})
        original = host.repo.read(scope,'artifact','practice-curated-selection')['version']
        service.install(scope)
        assert host.repo.read(scope,'artifact','practice-curated-selection')['version'] == original
        assert host.repo.read(scope,'note','private-note')['value']['text'] == 'preserve me'
        headers = {'X-Xueya-Token':client.get('/api/platform/bootstrap').json()['token']}
        catalog = client.get('/api/practice/bank?courseId=course-default',headers=headers).json()
        assert len(catalog['questions']) == 200
        assert len(catalog['generations'][0]['units']) == 10
        q = next(q for q in catalog['questions'] if q['type']=='multiple')
        response = client.post('/api/practice/ops',headers=headers,json={'ops':[
            {'opId':'curated-answer','kind':'answer','questionId':q['id'],
             'payload':{'questionType':'multiple','result':'wrong','selected':[0]}}]}).json()
        assert response['accepted'] == ['curated-answer']
        assert response['statuses'][q['id']]['wrongCount'] == 1
        host.repo.ensure_course(host.user_id, {'id':'other','name':'其他课程'})
        assert service.catalog('other')['questions'] == []
        doc = host.repo.read(scope,'document','textbook-fixture')
        host.repo.put(scope,'document','textbook-fixture',{**doc['value'],'contentRevision':3})
        assert service.catalog('course-default')['questions'] == []
        assert len(service.catalog('course-default',history=True)['questions']) == 200


def test_corrupt_package_is_rejected():
    package = json.loads(PACKAGE_FILE.read_text(encoding='utf-8'))
    package['questions'][0]['answer'] = 99
    with pytest.raises(AppError):
        validate_package(package)
