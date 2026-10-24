"""Pure practice state transitions (PRD 5-8). No bank, no HTTP."""
import pytest
from backend.xueya import practice_rules as rules

SINGLE = {'id': 'q1', 'type': 'single'}
FILL = {'id': 'q2', 'type': 'fill'}
CODE = {'id': 'q3', 'type': 'code'}
SHORT = {'id': 'q4', 'type': 'short'}


def at(n):
    return f'2026-10-24T00:00:{n:02d}.000Z'


def test_fresh_question_is_pending_with_zero_counts():
    progress = {}
    rules.entry(progress, 'q1')
    assert progress['q1']['status'] == 'pending'
    assert progress['q1']['wrongCount'] == 0
    assert progress['q1']['confidence'] == 'unknown'


def test_wrong_answer_auto_enters_wrong_book_and_counts():
    progress = {}
    row = rules.apply(progress, SINGLE, 'answer', {'result': 'wrong', 'at': at(1)})
    assert row['status'] == 'wrong'
    assert row['wrongCount'] == 1
    assert row['lastWrongAt'] == at(1)
    assert row['wrongEnteredAt'] == at(1)


def test_each_re_answer_wrong_counts_separately():
    progress = {}
    rules.apply(progress, SINGLE, 'answer', {'result': 'wrong', 'at': at(1)})
    rules.apply(progress, SINGLE, 'answer', {'result': 'wrong', 'at': at(2)})
    rules.apply(progress, SINGLE, 'answer', {'result': 'wrong', 'at': at(3)})
    assert progress['q1']['wrongCount'] == 3


def test_correct_re_answer_stays_in_wrong_book():
    progress = {}
    rules.apply(progress, SINGLE, 'answer', {'result': 'wrong', 'at': at(1)})
    row = rules.apply(progress, SINGLE, 'answer', {'result': 'correct', 'at': at(2)})
    assert row['status'] == 'wrong'
    assert row['wrongCount'] == 1
    assert row['correctCount'] == 1


def test_manual_add_and_forget_do_not_raise_wrong_count():
    progress = {}
    row = rules.apply(progress, CODE, 'mark-wrong', {'at': at(1)})
    assert row['status'] == 'wrong'
    assert row['wrongCount'] == 0
    assert row['wrongEnteredAt'] == at(1)
    row = rules.apply(progress, SHORT, 'mark-wrong', {'at': at(2)},)
    assert row['wrongCount'] == 0


def test_fuzzy_keeps_pending_and_ignores_objective_answer_shape():
    progress = {}
    row = rules.apply(progress, SINGLE, 'fuzzy', {'at': at(1)})
    assert row['status'] == 'pending'
    assert row['confidence'] == 'fuzzy'
    assert rules.weight(row) == 3
    assert rules.weight(rules.blank()) == 1


def test_master_moves_to_mastered_and_reset_returns_to_pending():
    progress = {}
    rules.apply(progress, SINGLE, 'fuzzy', {'at': at(1)})
    row = rules.apply(progress, SINGLE, 'master', {'at': at(2)})
    assert row['status'] == 'mastered'
    row = rules.apply(progress, SINGLE, 'reset', {'at': at(3)})
    assert row['status'] == 'pending'
    assert row['wrongCount'] == 0


def test_conquer_moves_wrong_to_mastered_keeps_history():
    progress = {}
    rules.apply(progress, SINGLE, 'answer', {'result': 'wrong', 'at': at(1)})
    row = rules.apply(progress, SINGLE, 'conquer', {'at': at(2)})
    assert row['status'] == 'mastered'
    assert row['wrongCount'] == 1


def test_correct_reverses_only_this_increment_and_returns_to_pending():
    progress = {}
    rules.apply(progress, FILL, 'answer', {'result': 'wrong', 'at': at(1)})
    rules.apply(progress, FILL, 'answer', {'result': 'wrong', 'at': at(2)})
    row = rules.apply(progress, FILL, 'correct', {'at': at(3)})
    assert row['wrongCount'] == 1
    assert row['status'] == 'pending'
    assert row['lastResult'] == 'correct'


def test_correct_rejects_single_and_untouched_questions():
    with pytest.raises(ValueError):
        rules.apply({}, SINGLE, 'correct', {'at': at(1)})
    progress = {}
    rules.apply(progress, FILL, 'answer', {'result': 'correct', 'at': at(1)})
    with pytest.raises(ValueError):
        rules.apply(progress, FILL, 'correct', {'at': at(2)})


def test_illegal_transitions_raise():
    progress = {}
    rules.apply(progress, SINGLE, 'master', {'at': at(1)})
    with pytest.raises(ValueError):
        rules.apply(progress, SINGLE, 'conquer', {'at': at(2)})   # conquer needs 错题本
    with pytest.raises(ValueError):
        rules.apply(progress, SINGLE, 'master', {'at': at(3)})    # master needs 待刷
    with pytest.raises(ValueError):
        rules.apply(progress, SINGLE, 'fuzzy', {'at': at(4)})     # 待巩固 needs 待刷
    rules.apply(progress, SINGLE, 'reset', {'at': at(5)})         # 已掌握 -> 待刷 is legal
    with pytest.raises(ValueError):
        rules.apply(progress, SINGLE, 'reset', {'at': at(6)})     # already 待刷
    with pytest.raises(ValueError):
        rules.apply(progress, CODE, 'answer', {'result': 'wrong', 'at': at(7)})
    with pytest.raises(ValueError):
        rules.apply({}, SINGLE, 'answer', {'result': 'maybe', 'at': at(8)})


def test_random_pick_weights_fuzzy_higher_and_avoids_last():
    questions = [{'id': f'q{i}'} for i in range(3)]
    progress = {'q1': {**rules.blank(), 'confidence': 'fuzzy'}}
    # A uniform roll lands past q0 when q1 is weighted 3x: bias check over many rolls.
    hits = {q['id']: 0 for q in questions}
    for i in range(300):
        picked = rules.random_pick(questions, progress, last_id='q9', roll=i / 300)
        hits[picked['id']] += 1
    assert hits['q1'] > hits['q0'] and hits['q1'] > hits['q2']
    assert rules.random_pick(questions, progress, last_id='q1', roll=0.999) is not None


def test_random_pick_empty_returns_none():
    assert rules.random_pick([], {}) is None


def test_sort_wrong_by_recent_and_by_count():
    rows = [('a', {'wrongCount': 1, 'lastWrongAt': at(3), 'wrongEnteredAt': at(1)}),
            ('b', {'wrongCount': 5, 'lastWrongAt': at(1), 'wrongEnteredAt': at(2)}),
            ('c', {'wrongCount': 2, 'lastWrongAt': at(2), 'wrongEnteredAt': at(3)})]
    assert [r[0] for r in rules.sort_wrong(rows, mode='recent')] == ['a', 'c', 'b']
    assert [r[0] for r in rules.sort_wrong(rows, mode='count')] == ['b', 'c', 'a']


def test_note_merge_on_matching_revision_replaces():
    merged = rules.merge_note({'text': 'old', 'revision': 3}, 'new', 3, at=at(1), device='d1')
    assert merged['text'] == 'new'
    assert merged['revision'] == 4
    assert merged['merged'] is False
    assert merged['conflicts'] == []


def test_note_merge_on_stale_revision_keeps_both_copies():
    merged = rules.merge_note({'text': 'server copy', 'revision': 5, 'conflicts': []},
                              'other browser copy', 4, at=at(2), device='d2')
    assert merged['text'] == 'server copy'
    assert merged['merged'] is True
    assert len(merged['conflicts']) == 1
    assert merged['conflicts'][0]['text'] == 'other browser copy'
    assert merged['conflicts'][0]['deviceTag'] == 'd2'
