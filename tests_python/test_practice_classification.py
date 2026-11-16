"""Hot100 knowledge-point classification stays complete and data-driven.

The practice page derives its topic navigation from the official ``q.topic`` values of
the shipped bank (17 official topics) instead of a hardcoded label list, groups the
"全部知识点" list by that topic, and must never drop a question under any filter
combination. These tests pin the data invariants and rehearse the grouping rules on
both the real 100-question bank and a mock bank.
"""
from __future__ import annotations

import json
from itertools import product
from pathlib import Path

from backend.xueya import practice_bank

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_FILE = ROOT / 'backend' / 'xueya' / 'data' / 'hot100_official.json'
VIEW_FILE = ROOT / 'frontend' / 'js' / 'practice-view.js'
QUESTION_COUNT = 100
TOPIC_COUNT = 17


def hot100():
    return [q for q in practice_bank.questions() if q['category'] == 'hot100']


def official_topics():
    rows = json.loads(OFFICIAL_FILE.read_text(encoding='utf-8'))['questions']
    return list(dict.fromkeys(row['topic'] for row in rows))


def matches(question, filters):
    """Mirror practice-view.js matches() plus the list status filter."""
    if filters.get('subject') and question['subject'] != filters['subject']:
        return False
    if filters.get('difficulty') and question['difficulty'] != filters['difficulty']:
        return False
    if filters.get('type') and question['type'] != filters['type']:
        return False
    if filters.get('tag') and filters['tag'] not in (question.get('tags') or []):
        return False
    keyword = str(filters.get('keyword') or '').strip().lower()
    if keyword:
        haystack = ' '.join([question['id'], str(question.get('leetcodeNumber') or ''), question['title'],
                             question['prompt'], *(question.get('tags') or [])]).lower()
        if keyword not in haystack:
            return False
    return True


def grouped(rows):
    """Group rows by q.topic, preserving first-seen topic order (what the UI does)."""
    order, groups = [], {}
    for question in rows:
        topic = question['topic']
        if topic not in groups:
            order.append(topic)
            groups[topic] = []
        groups[topic].append(question)
    return order, groups


def test_hot100_has_exactly_17_official_topics_with_a_complete_union():
    rows = hot100()
    topics = official_topics()
    assert len(rows) == QUESTION_COUNT
    assert len(topics) == TOPIC_COUNT
    assert len({q['id'] for q in rows}) == QUESTION_COUNT
    assert {q['topic'] for q in rows} == set(topics), 'every question must map to one official topic'
    assert all(q['topic'] in q['tags'] for q in rows), 'select-based tag filtering must find every topic'
    order, groups = grouped(rows)
    assert order == topics, 'the bank order is already grouped by official topic order'
    assert sum(len(items) for items in groups.values()) == QUESTION_COUNT
    flattened = [question['id'] for items in groups.values() for question in items]
    assert len(flattened) == len(set(flattened)) == QUESTION_COUNT, 'no question is classified twice'


def test_topic_counts_cover_all_questions_and_sum_to_100():
    rows = hot100()
    topics = official_topics()
    counts = {topic: sum(1 for q in rows if q['topic'] == topic) for topic in topics}
    assert set(counts) == set(topics)
    assert sum(counts.values()) == QUESTION_COUNT
    assert all(count > 0 for count in counts.values()), counts
    # "全部知识点" plus the 17 topic buttons: the navigation covers the whole bank.
    assert len(counts) == TOPIC_COUNT


def test_h100_53_is_graph_theory_without_any_200_special_case():
    target = next(q for q in hot100() if q['id'] == 'h100-53')
    assert target['leetcodeNumber'] == 200
    assert target['title'] == '岛屿数量'
    assert target['topic'] == '图论'
    assert '图论' in target['tags']
    source = VIEW_FILE.read_text(encoding='utf-8')
    assert '#200' not in source, 'the UI must not special-case LeetCode #200'
    assert 'HOT_TOPICS' not in source, 'topic navigation must come from q.topic, not a hardcoded list'
    assert 'XueyaAlgorithmDemoIds' in source, 'demo markers must read the generated registry'
    assert "'h100-63'" not in source and "'h100-53'" not in source, 'no demo id may be hardcoded in the view'


def test_any_filter_combination_keeps_every_question_inside_a_topic_group():
    rows = hot100()
    statuses = {q['id']: ('mastered' if index % 5 == 0 else 'wrong' if index % 7 == 0 else 'pending')
                for index, q in enumerate(rows)}
    tags = sorted({tag for q in rows for tag in q['tags']})[:16]
    official = set(official_topics())
    combinations = 0
    for difficulty, keyword, tag, status in product(['', '简单', '中等', '困难'],
                                                    ['', '树', '图', 'dp', '链表', '200'],
                                                    tags,
                                                    ['pending', 'mastered', 'wrong']):
        filters = {'difficulty': difficulty, 'keyword': keyword, 'tag': tag}
        listed = [q for q in rows if matches(q, filters) and statuses[q['id']] == status]
        order, groups = grouped(listed)
        flattened = [question for topic in order for question in groups[topic]]
        assert len(flattened) == len(listed), 'grouping must not lose or duplicate questions'
        assert {q['id'] for q in flattened} == {q['id'] for q in listed}
        assert all(q['topic'] in official for q in flattened)
        for topic in order:
            assert all(question['topic'] == topic for question in groups[topic])
        combinations += 1
    assert combinations >= 1000


def test_mock_bank_grouping_keeps_repeated_topics_and_all_rows():
    """The list inserts a heading only when the topic changes; rows are never dropped."""
    mock = [
        {'id': 'm1', 'topic': '哈希'},
        {'id': 'm2', 'topic': '哈希'},
        {'id': 'm3', 'topic': '双指针'},
        {'id': 'm4', 'topic': '哈希'},   # non-consecutive repeat must still show every row
        {'id': 'm5', 'topic': '图论'},
        {'id': 'm6', 'topic': '图论'},
    ]
    headings, counts, last_topic, seen = [], {}, None, []
    for question in mock:
        if question['topic'] != last_topic:
            headings.append(question['topic'])
            last_topic = question['topic']
        seen.append(question['id'])
        counts[question['topic']] = counts.get(question['topic'], 0) + 1
    assert seen == [question['id'] for question in mock]
    assert headings == ['哈希', '双指针', '哈希', '图论']
    assert sum(counts.values()) == len(mock)


def test_frontend_builds_topic_navigation_from_data_and_scrolls_selection_into_view():
    source = VIEW_FILE.read_text(encoding='utf-8')
    assert 'q.topic' in source
    assert 'data-action="hot-topic"' in source
    assert 'hot100-topic-nav' in source
    assert "scrollIntoView({block:'nearest'})" in source
