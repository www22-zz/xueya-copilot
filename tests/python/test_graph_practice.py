import json
from pathlib import Path
from backend.xueya.graph_practice import attach_practice


def test_stack_outline_links_only_visible_fixed_questions():
    bank = json.loads((Path(__file__).parents[2] / 'backend/xueya/data/data_structures_practice.json').read_text(encoding='utf-8'))
    questions = [dict(q, bankSource='legacy') for q in bank['questions']]
    doc = {'id': 'chapter3', 'name': '第3章_栈和队列.pptx', 'ready': True}
    concepts, edges = {}, []
    attach_practice([doc], concepts, edges, questions)
    linked = {q['id'] for n in concepts.values() for q in n['fixedQuestions']}
    expected = {q['id'] for q in questions if q['topic'] == '栈与队列'}
    assert linked == expected and len(linked) == 20
    assert all(q['url'] == '#space/practice/legacy/' + q['id'] for n in concepts.values() for q in n['fixedQuestions'])
    assert all(n['questionIds'] == [] for n in concepts.values())
    assert len(edges) == len(concepts)
    for documents, visible in [([], questions), ([dict(doc, ready=False)], questions), ([doc], [])]:
        nodes, relations = {}, []
        attach_practice(documents, nodes, relations, visible)
        assert not nodes and not relations
