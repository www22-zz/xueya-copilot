"""Trusted read-only tool catalogue and bounded observations over an MCP session."""
from jsonschema import Draft202012Validator
from ..core import require, clone, dumps, fingerprint, resolve, valid_date

TOOL_DESCRIPTIONS = {
    'search_materials': '在本次允许的课程原文中搜索。无命中时可改写检索词；搜索结果不能代替read_source核对。参数query为具体知识关键词。',
    'read_source': '按真实sourceId读取本次允许的原文。来源必须来自目录或搜索结果；只有核对后的原文能支持最终课程回答。',
    'analyze_progress': '读取真实近期作答，返回作答数、正确数、薄弱点与到期主题。没有记录时不能推断能力。',
    'build_review_plan': '按课程设置、考试日期和每日时长生成只读复习预览，不保存或采纳计划。',
    'list_wrong_questions': '分页读取真实错题。可以定位待巩固主题，但不能猜测真实思考过程或代替用户确认错因。',
    'get_review_queue': '读取当前真正到期的FSRS复习卡。空队列是查询结果，不能擅自评分。',
    'get_course_graph': '读取课程概念、先修关系与来源信息，辅助决定先阅读哪些知识；不修改图谱。',
}
READ_ONLY_TOOLS = frozenset(TOOL_DESCRIPTIONS)
TOOL_LABELS = {'search_materials': '正在查找课程资料', 'read_source': '正在核对引用原文',
    'analyze_progress': '正在分析近期作答', 'build_review_plan': '正在生成复习计划预览',
    'list_wrong_questions': '正在读取课程错题', 'get_review_queue': '正在查看到期复习卡', 'get_course_graph': '正在查看知识结构'}


class ReadOnlyTools:
    def __init__(self, session, sources, *, course_id='course-default', verify=None):
        self.session, self.course_id, self.verify = session, course_id, verify
        self.sources = {s['id']: clone(s) for s in sources}
        self.evidence, self.results, self.facts, self.calls = {}, {}, set(), set()
        self.definitions = {}

    async def catalogue(self):
        definitions = await self.session.list_tools()
        self.definitions = {d['name']: clone(d) for d in definitions if d['name'] in READ_ONLY_TOOLS}
        return [{'name': name, 'description': TOOL_DESCRIPTIONS[name], 'inputSchema': d['inputSchema']}
                for name, d in self.definitions.items()]

    async def current(self):
        require(self.verify is None or await resolve(self.verify()), 'STALE_EVIDENCE')

    async def call(self, name, arguments):
        require(name in self.definitions and name in READ_ONLY_TOOLS, 'TOOL_FORBIDDEN')
        require(isinstance(arguments, dict) and len(dumps(arguments).encode()) <= 8192, 'INVALID_TOOL_ARGUMENTS')
        require(not {'courseId', 'userId', 'confirmed', 'confirmation', 'allowApi'} & arguments.keys(), 'INVALID_TOOL_ARGUMENTS')
        require(Draft202012Validator(self.definitions[name]['inputSchema']).is_valid(arguments), 'INVALID_TOOL_ARGUMENTS')
        key = fingerprint([name, arguments])
        if key in self.calls:
            return {'status': 'duplicate', 'data': {'message': '相同调用已执行，请使用已有结果或选择其他动作。'}, 'newInformation': False}
        await self.current()
        self.calls.add(key)
        value = await self.session.call(name, clone(arguments))
        await self.current()
        require(isinstance(value, dict) and len(dumps(value).encode()) <= 131072, 'MCP_INVALID_RESULT')
        require(value.get('courseId', self.course_id) == self.course_id, 'RESULT_SCOPE_MISMATCH')
        data = self._validate(name, arguments, value)
        signature = fingerprint([name, data])
        fresh = signature not in self.facts
        self.facts.add(signature)
        self.results[name] = clone(value)
        if name == 'search_materials' and not value['sources']:
            fresh = False
        return {'status': 'completed', 'data': self._bounded(data), 'newInformation': fresh}

    def _validate(self, name, args, value):
        if name in ('search_materials', 'read_source'):
            sources = value.get('sources') if name == 'search_materials' else [value.get('source')]
            require(isinstance(sources, list) and len(sources) <= 6, 'MCP_INVALID_RESULT')
            for source in sources:
                require(isinstance(source, dict), 'MCP_INVALID_RESULT')
                actual = self.sources.get(source.get('id'))
                require(actual and source.get('quote') == actual['quote'], 'MCP_INVALID_RESULT')
            if name == 'read_source':
                require(sources[0]['id'] == args['sourceId'], 'MCP_INVALID_RESULT')
                self.evidence[sources[0]['id']] = clone(self.sources[sources[0]['id']])
                return {'source': clone(self.sources[sources[0]['id']])}
            return {'sources': [{**{k: s.get(k) for k in ('id', 'title', 'location')}, 'excerpt': s['quote'][:200]} for s in sources],
                    'warnings': [s for s in value.get('warnings', []) if isinstance(s, str)][:8]}
        if name == 'analyze_progress':
            require(type(value.get('total')) is int and type(value.get('correct')) is int and 0 <= value['correct'] <= value['total'], 'MCP_INVALID_RESULT')
            require(all(isinstance(value.get(key), list) and all(isinstance(s, str) for s in value[key]) for key in ('weakTopics', 'dueTopics')), 'MCP_INVALID_RESULT')
            return {k: value[k] for k in ('total', 'correct', 'weakTopics', 'dueTopics')}
        if name == 'build_review_plan':
            require(valid_date(value.get('examDate')) and type(value.get('minutes')) is int and 15 <= value['minutes'] <= 120 and isinstance(value.get('days'), list) and len(value['days']) <= 90, 'MCP_INVALID_RESULT')
            for day in value['days']:
                require(isinstance(day, dict) and valid_date(day.get('date')) and isinstance(day.get('tasks'), list), 'MCP_INVALID_RESULT')
                require(all(isinstance(t, dict) and isinstance(t.get('title'), str) and type(t.get('minutes')) is int and 0 < t['minutes'] <= 120 for t in day['tasks']), 'MCP_INVALID_RESULT')
            return value
        if name == 'list_wrong_questions':
            require(isinstance(value.get('items'), list) and len(value['items']) <= args.get('limit', 20), 'MCP_INVALID_RESULT')
            require(all(isinstance(q, dict) and isinstance(q.get('id'), str) for q in value['items']), 'MCP_INVALID_RESULT')
            return {'items': [{k: q[k] for k in ('id', 'topic', 'prompt', 'sourceId') if k in q} for q in value['items'] if isinstance(q, dict)], 'nextCursor': value.get('nextCursor')}
        if name == 'get_review_queue':
            require(isinstance(value.get('cards'), list), 'MCP_INVALID_RESULT')
            require(all(isinstance(c, dict) and isinstance(c.get('id'), str) for c in value['cards']), 'MCP_INVALID_RESULT')
            return {'count': len(value['cards']), 'cards': [{k: c[k] for k in ('id', 'dueDate', 'eligibleAt') if k in c} for c in value['cards'][:10] if isinstance(c, dict)]}
        graph = value.get('content', value)
        require(isinstance(graph, dict) and graph.get('courseId', self.course_id) == self.course_id and isinstance(graph.get('concepts'), list) and isinstance(graph.get('edges'), list), 'MCP_INVALID_RESULT')
        return {'conceptCount': len(graph['concepts']), 'edgeCount': len(graph['edges']), 'concepts': graph['concepts'][:20], 'edges': graph['edges'][:20]}

    @staticmethod
    def _bounded(data):
        text = dumps(data)
        return data if len(text.encode()) <= 6000 else {'truncated': True, 'preview': text[:1500]}
