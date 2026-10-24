"""The built-in practice bank must satisfy the PRD counts and shapes exactly."""
from backend.xueya import practice_bank


def test_bank_loads_and_matches_the_prd_counts():
    bank = practice_bank.load()
    assert bank['version'] == practice_bank.BANK_VERSION
    questions = bank['questions']
    assert len(questions) == 250
    assert sum(q['category'] == 'hot100' for q in questions) == 100
    assert sum(q['category'] == 'basic' and q['type'] == 'single' for q in questions) == 50
    assert sum(q['category'] == 'basic' and q['type'] == 'fill' for q in questions) == 50
    assert sum(q['category'] == 'interview' for q in questions) == 50


def test_hot100_carries_three_language_solutions_and_real_leetcode_links():
    for q in practice_bank.questions():
        if q['category'] != 'hot100':
            continue
        for language in ('python', 'cpp', 'java'):
            assert q['solutions'][language].strip(), q['id']
        assert q['complexity']['time'] and q['complexity']['space']
        assert q['leetcodeUrl'].startswith('https://leetcode.cn/problems/')
        assert len(q['hints']) >= 2
        assert q['samples']


def test_every_subject_has_10_single_10_fill_and_10_interview():
    counts = {}
    for q in practice_bank.questions():
        if q['category'] == 'hot100':
            continue
        counts.setdefault((q['subject'], q['type']), 0)
        counts[(q['subject'], q['type'])] += 1
    for subject in practice_bank.SUBJECTS:
        assert counts[(subject, 'single')] == 10
        assert counts[(subject, 'fill')] == 10
        assert counts[(subject, 'short')] == 10


def test_ids_are_unique_and_stable():
    ids = [q['id'] for q in practice_bank.questions()]
    assert len(ids) == len(set(ids))
    assert practice_bank.question('h100-01') is not None
    assert practice_bank.question('b-dsa-s01') is not None
    assert practice_bank.question('i-os-01') is not None
    assert practice_bank.question('missing') is None


def test_fill_answers_always_include_the_canonical_form():
    for q in practice_bank.questions():
        if q['type'] == 'fill':
            assert q['acceptedAnswers'][0] == q['answer']


def test_single_choice_answers_index_an_option():
    for q in practice_bank.questions():
        if q['type'] == 'single':
            assert 0 <= q['answer'] <= 3
            assert len(q['options']) == 4


def test_filters_hide_but_never_reorder():
    everything = practice_bank.questions()
    subset = practice_bank.filtered({'category': 'basic', 'subject': '操作系统'})
    assert subset
    assert all(q['subject'] == '操作系统' and q['category'] == 'basic' for q in subset)
    positions = [everything.index(q) for q in subset]
    assert positions == sorted(positions)


def test_keyword_matches_id_title_prompt_and_tags_only():
    sample = practice_bank.questions()[0]
    hit = practice_bank.filtered({'keyword': sample['id']})
    assert sample in hit
    assert practice_bank.filtered({'keyword': 'zzz-not-present-anywhere'}) == []
