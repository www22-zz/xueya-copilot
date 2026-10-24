"""学习路径的完整输出、顺序和对象语义特征测试。"""
import pytest

from backend.agent.concepts import build_learning_path
from backend.core import DomainError, clone


@pytest.fixture
def path_input():
    return {
        'courseId': 'c',
        'graph': {
            'courseId': 'c',
            'concepts': [
                {'id': 'a', 'courseId': 'c', 'name': '基础', 'evidence': [{'quote': '基础原文'}]},
                {'id': 'b', 'courseId': 'c', 'name': '分支', 'status': 'candidate'},
                {'id': 'c', 'courseId': 'c', 'name': '目标', 'status': 'confirmed'},
            ],
            'edges': [
                {'from': 'b', 'to': 'c', 'type': 'prerequisite', 'status': 'confirmed'},
                {'from': 'a', 'to': 'c', 'type': 'prerequisite', 'status': 'confirmed'},
                {'from': 'a', 'to': 'c', 'type': 'prerequisite', 'status': 'confirmed'},
                {'from': 'c', 'to': 'a', 'type': 'prerequisite', 'status': 'candidate'},
                {'from': 'c', 'to': 'b', 'type': 'related', 'status': 'confirmed'},
            ],
        },
        'targetIds': ['c'],
        'estimates': [
            {'conceptId': 'a', 'estimate': 0.2, 'status': 'estimated', 'evidence': ['e1']},
            {'conceptId': 'b', 'estimate': 0.6, 'status': 'estimated', 'evidence': ['e2']},
        ],
    }


def test_full_path_preserves_edge_order_duplicates_reasons_and_review_states(path_input):
    before = clone(path_input)
    result = build_learning_path(path_input)
    assert result == {
        'courseId': 'c', 'targetIds': ['c'], 'ignoredCandidateEdges': 1,
        'algorithm': 'confirmed-prerequisites-v1',
        'entries': [
            {'conceptId': 'b', 'name': '分支', 'prerequisites': [], 'requiredBy': ['c'],
             'state': 'practice-supported', 'reviewStatus': 'candidate', 'reason': '目标知识点的先修基础',
             'sourceEvidence': [], 'eventEvidence': ['e2'], 'estimate': path_input['estimates'][1]},
            {'conceptId': 'a', 'name': '基础', 'prerequisites': [], 'requiredBy': ['c', 'c'],
             'state': 'needs-practice', 'reviewStatus': 'curated', 'reason': '目标知识点的先修基础',
             'sourceEvidence': [{'quote': '基础原文'}], 'eventEvidence': ['e1'], 'estimate': path_input['estimates'][0]},
            {'conceptId': 'c', 'name': '目标', 'prerequisites': ['b', 'a', 'a'], 'requiredBy': [],
             'state': 'unknown', 'reviewStatus': 'confirmed', 'reason': '尚无充分练习证据，先核对原文再练习',
             'sourceEvidence': [], 'eventEvidence': [], 'estimate': None},
        ],
    }
    assert path_input == before
    assert result['targetIds'] is path_input['targetIds']
    first = result['entries'][0]
    assert first['estimate'] is path_input['estimates'][1]
    assert first['eventEvidence'] is path_input['estimates'][1]['evidence']
    result['entries'][1]['sourceEvidence'][0]['quote'] = '修改副本'
    assert path_input == before


def test_default_targets_sort_by_estimate_then_id_and_keep_last_estimate(path_input):
    del path_input['targetIds']
    path_input['estimates'].append({'conceptId': 'a', 'estimate': 0.9, 'status': 'estimated'})
    result = build_learning_path(path_input)
    assert result['targetIds'] == ['c', 'b', 'a']
    assert [e['conceptId'] for e in result['entries']] == ['b', 'a', 'c']
    assert result['entries'][1]['reason'] == '已有练习证据，仍需复习核验'


def test_explicit_target_order_and_duplicates_are_retained(path_input):
    path_input['targetIds'] = ['a', 'c', 'a']
    result = build_learning_path(path_input)
    assert result['targetIds'] == ['a', 'c', 'a']
    assert [e['conceptId'] for e in result['entries']] == ['a', 'b', 'c']
    assert result['entries'][0]['reason'] == '近期作答证据提示需要巩固'


def test_empty_targets_do_not_build_entries(path_input):
    path_input['targetIds'] = []
    assert build_learning_path(path_input) == {
        'courseId': 'c', 'targetIds': [], 'entries': [],
        'ignoredCandidateEdges': 1, 'algorithm': 'confirmed-prerequisites-v1',
    }


def test_duplicate_concept_ids_keep_the_first_name(path_input):
    path_input['graph']['concepts'].append({'id': 'a', 'courseId': 'c', 'name': '重复节点'})
    result = build_learning_path(path_input)
    assert next(e for e in result['entries'] if e['conceptId'] == 'a')['name'] == '基础'


@pytest.mark.parametrize(('change', 'code'), [
    ({'courseId': 'other'}, 'INVALID_LEARNING_PATH'),
    ({'targetIds': ['missing']}, 'UNKNOWN_CONCEPT'),
    ({'targetIds': 'c'}, 'REJECTED_LEARNING_TARGET'),
])
def test_invalid_path_context_keeps_error_codes(path_input, change, code):
    with pytest.raises(DomainError, match=f'^{code}$'):
        build_learning_path({**path_input, **change})


@pytest.mark.parametrize(('rejected', 'code'), [
    ('c', 'REJECTED_LEARNING_TARGET'), ('a', 'REJECTED_PREREQUISITE'),
])
def test_rejected_nodes_keep_target_and_prerequisite_errors(path_input, rejected, code):
    next(c for c in path_input['graph']['concepts'] if c['id'] == rejected)['status'] = 'rejected'
    with pytest.raises(DomainError, match=f'^{code}$'):
        build_learning_path(path_input)


def test_confirmed_cycle_is_rejected_and_candidate_cycle_is_ignored(path_input):
    path_input['graph']['edges'][3]['status'] = 'confirmed'
    with pytest.raises(DomainError, match='^PREREQUISITE_CYCLE$'):
        build_learning_path(path_input)
