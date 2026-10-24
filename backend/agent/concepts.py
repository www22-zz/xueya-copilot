from ..core import require, clone, normalized


def prerequisite_order(graph, targets=None):
    ids = {c['id'] for c in graph['concepts']}
    targets = [c['id'] for c in graph['concepts']] if targets is None else targets
    require(all(x in ids for x in targets), 'UNKNOWN_CONCEPT')
    parents = {key: [] for key in ids}
    for edge in graph['edges']:
        if edge['type'] == 'prerequisite' and edge['status'] == 'confirmed':
            require(edge['to'] in ids and edge['from'] in ids, 'INVALID_CONCEPT_EDGE')
            parents[edge['to']].append(edge['from'])
    visiting, visited, order = set(), set(), []

    def visit(key):
        require(key not in visiting, 'PREREQUISITE_CYCLE')
        if key in visited:
            return
        visiting.add(key)
        for parent in parents[key]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)
        order.append(key)
    for key in targets:
        visit(key)
    return order


def validate_graph(graph, sources=()):
    course = graph.get('courseId')
    require(course and isinstance(graph.get('concepts'), list) and isinstance(graph.get('edges'), list), 'INVALID_GRAPH')

    def evidence(refs):
        return isinstance(refs, list) and refs and all(any(s.get('courseId') == course and s['id'] == ref.get('sourceId') and s.get('version') == ref.get('version') and isinstance(ref.get('quote'), str) and ref['quote'].strip() and ref['quote'] in s['quote'] for s in sources) for ref in refs)
    ids, aliases = set(), {}
    for c in graph['concepts']:
        require(c.get('status') in (None, 'candidate', 'confirmed', 'rejected'), 'INVALID_CONCEPT_STATUS')
        require(c.get('id') and c['id'] not in ids and c.get('courseId') == course and isinstance(c.get('name'), str) and c['name'].strip() and evidence(c.get('evidence')), 'INVALID_CONCEPT')
        ids.add(c['id'])
        for alias in [c['name'], *c.get('aliases', [])]:
            require(isinstance(alias, str) and alias.strip(), 'INVALID_ALIAS')
            key = normalized(alias)
            require(key not in aliases or aliases[key] == c['id'], 'AMBIGUOUS_CONCEPT_ALIAS')
            aliases[key] = c['id']
    seen = set()
    for edge in graph['edges']:
        key = (edge.get('from'), edge.get('to'), edge.get('type'))
        require(key not in seen and key[0] in ids and key[1] in ids and key[0] != key[1] and key[2] in ('prerequisite', 'part-of', 'contrast', 'example', 'related') and edge.get('status') in ('candidate', 'confirmed'), 'INVALID_CONCEPT_EDGE')
        require(evidence(edge.get('evidence')) or edge.get('inferred') is True and edge.get('reason'), 'EDGE_EVIDENCE_REQUIRED')
        require(not (edge.get('inferred') and edge['status'] == 'confirmed') or edge.get('reviewedBy'), 'INFERRED_EDGE_REVIEW_REQUIRED')
        seen.add(key)
    prerequisite_order(graph)
    return clone(graph)


def build_learning_path(value):
    graph, course = value.get('graph'), value.get('courseId')
    require(course and graph and graph.get('courseId') == course, 'INVALID_LEARNING_PATH')
    require(all(c['courseId'] == course for c in graph['concepts']), 'COURSE_MISMATCH')
    rejected = {c['id'] for c in graph['concepts'] if c.get('status') == 'rejected'}
    estimates = {e['conceptId']: e for e in value.get('estimates', [])}
    targets = value.get('targetIds')
    if targets is None:
        targets = [c['id'] for c in sorted(graph['concepts'], key=lambda c: (estimates.get(c['id'], {}).get('estimate') if estimates.get(c['id'], {}).get('estimate') is not None else .5, c['id'])) if c['id'] not in rejected]
    require(isinstance(targets, list) and not set(targets) & rejected, 'REJECTED_LEARNING_TARGET')
    order = prerequisite_order(graph, targets)
    require(not set(order) & rejected, 'REJECTED_PREREQUISITE')
    concepts = {}
    for concept in graph['concepts']:
        # 保留原先 next 查找的首个同 ID 节点，不在路径构建中额外去重校验。
        concepts.setdefault(concept['id'], concept)
    prerequisites = {key: [] for key in order}
    required_by = {key: [] for key in order}
    for edge in graph['edges']:
        if edge['type'] == 'prerequisite' and edge['status'] == 'confirmed':
            if edge['to'] in prerequisites:
                prerequisites[edge['to']].append(edge['from'])
            if edge['from'] in required_by:
                required_by[edge['from']].append(edge['to'])
    target_ids = set(targets)
    entries = []
    for key in order:
        c = concepts[key]
        estimate = estimates.get(key)
        state = ('needs-practice' if estimate['estimate'] < .6 else 'practice-supported') if estimate and estimate['status'] == 'estimated' else 'unknown'
        reason = '目标知识点的先修基础' if key not in target_ids else '近期作答证据提示需要巩固' if state == 'needs-practice' else '尚无充分练习证据，先核对原文再练习' if state == 'unknown' else '已有练习证据，仍需复习核验'
        entries.append({'conceptId': key, 'name': c['name'], 'prerequisites': prerequisites[key], 'requiredBy': required_by[key],
                        'state': state, 'reviewStatus': c.get('status', 'curated'), 'reason': reason, 'sourceEvidence': clone(c.get('evidence', [])), 'eventEvidence': estimate.get('evidence', []) if estimate else [], 'estimate': estimate})
    return {'courseId': course, 'targetIds': targets, 'entries': entries, 'ignoredCandidateEdges': sum(e['status'] != 'confirmed' for e in graph['edges']), 'algorithm': 'confirmed-prerequisites-v1'}
