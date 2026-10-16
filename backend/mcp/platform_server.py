"""Scope-bound real MCP server; host confirmation is deliberately not a tool."""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import json
from mcp.server.lowlevel import Server
from mcp import types
from mcp import Client
from ..core import require, dumps, resolve, DomainError, clone

PAGE = {'cursor': {'type': 'string', 'maxLength': 300}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50, 'default': 20}}
_active_sessions = 0


def create_platform_server(platform, scope, library=None, reference_enabled=False):
    platform.repository.require_course(scope)
    bound, server, repository = clone(scope), Server('xueya-learning-platform'), platform.repository
    schema = lambda props=None, required=None: {'type': 'object', 'properties': props or {}, 'required': required or [], 'additionalProperties': False}
    definitions = [
        ('search_materials', schema({'query': {'type': 'string', 'minLength': 1, 'maxLength': 4000}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 6}}, ['query'])),
        ('read_source', schema({'sourceId': {'type': 'string', 'minLength': 1, 'maxLength': 150}}, ['sourceId'])),
        *[(name, schema(PAGE)) for name in ('list_sections', 'list_concepts', 'list_question_drafts', 'list_attempts', 'list_wrong_questions', 'list_reviews', 'list_plans', 'list_notes')],
        ('read_section', schema({**PAGE, 'sectionId': {'type': 'string'}}, ['sectionId'])),
        ('get_prerequisites', schema({**PAGE, 'conceptId': {'type': 'string'}}, ['conceptId'])),
        ('analyze_progress', schema()), ('build_review_plan', schema()),
        ('prepare_action', schema({'kind': {'enum': ['note', 'question', 'plan']}, 'entityId': {'type': 'string'}, 'expectedVersion': {'type': 'integer', 'minimum': 0}, 'after': {'type': 'object'}}, ['kind', 'entityId', 'expectedVersion', 'after'])),
        ('preview_action', schema({'actionId': {'type': 'string', 'format': 'uuid'}}, ['actionId'])),
        ('apply_action', schema({'actionId': {'type': 'string', 'format': 'uuid'}}, ['actionId']))]
    if reference_enabled:
        definitions.append(('lookup_reference', schema({'doi': {'type': 'string', 'minLength': 6, 'maxLength': 200, 'pattern': r'^10\.\d{4,9}/[!-~]+$'}}, ['doi'])))

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(name=name, description='当前课程的'+name, inputSchema=definition,
                           annotations=types.ToolAnnotations(readOnlyHint=name not in ('prepare_action', 'apply_action'), destructiveHint=name == 'apply_action', idempotentHint=name != 'prepare_action', openWorldHint=name == 'lookup_reference'),
                           meta={'schemaVersion': '2.0', 'risk': 'write' if name in ('prepare_action', 'apply_action') else 'external' if name == 'lookup_reference' else 'read'}) for name, definition in definitions])

    async def call(ctx, params):
        name, args = params.name, params.arguments or {}
        try:
            repository.require_course(bound)
            if name == 'search_materials':
                data = {'sources': (await platform.rag.retrieve(args['query'], repository.all(bound, 'source') if library is None else library))[:args.get('limit', 4)]}
            elif name == 'read_source':
                source = repository.read_source(bound, args['sourceId']) if library is None else next((s for s in library if s['id'] == args['sourceId']), None)
                require(source, 'SOURCE_NOT_FOUND')
                data = {'source': source}
            elif name in ('analyze_progress', 'build_review_plan'):
                from ..agent.tasks import normalize_context, local_study
                workspace = repository.get_workspace(bound['userId'])
                course = next((c for c in workspace['data']['courses'] if c['id'] == bound['courseId']), None) if workspace else None
                context = normalize_context({'questions': repository.all(bound, 'question'), 'records': repository.all(bound, 'attempt'), **({k: course['data'].get(k) for k in ('examDate', 'minutes')} if course else {})})
                result = local_study(context, 'review' if name == 'analyze_progress' else 'plan')
                data = result['progress'] if name == 'analyze_progress' else result['plan']
            elif name == 'prepare_action':
                data = await platform.authority.prepare(bound, args)
            elif name == 'preview_action':
                data = platform.authority.preview(bound, args['actionId'])
            elif name == 'apply_action':
                data = await platform.authority.apply(bound, args['actionId'])
            elif name == 'lookup_reference':
                require(reference_enabled, 'REFERENCE_DISABLED')
                from .reference_tool import lookup_reference
                data = await lookup_reference(args['doi'], enabled=True)
            else:
                kinds = {'list_sections': 'document', 'read_section': 'source', 'list_concepts': 'concept', 'get_prerequisites': 'concept', 'list_question_drafts': 'question', 'list_attempts': 'attempt', 'list_wrong_questions': 'question', 'list_reviews': 'review', 'list_plans': 'plan', 'list_notes': 'note'}
                require(name in kinds, 'TOOL_NOT_FOUND')
                items = None
                if name == 'read_section':
                    items = [s for s in repository.all(bound, 'source') if s.get('documentId') == args['sectionId']]
                elif name == 'list_sections':
                    items = [d for d in repository.all(bound, 'document') if not d.get('superseded')]
                elif name == 'get_prerequisites':
                    concept = repository.read(bound, 'concept', args['conceptId'])
                    require(concept, 'CONCEPT_NOT_FOUND')
                    refs = concept['value'].get('prerequisites', [])
                    items = [c for c in repository.all(bound, 'concept') if c['id'] in refs]
                elif name == 'list_wrong_questions':
                    latest = {r['questionId']: r for r in repository.all(bound, 'attempt') if r.get('questionId')}
                    items = [q for q in repository.all(bound, 'question') if q['id'] in latest and not latest[q['id']].get('correct')]
                data = repository.page(bound, kinds[name], args.get('cursor'), args.get('limit', 20), items, name+':'+str(args.get('sectionId', args.get('conceptId', ''))))
            wrapped = {'schemaVersion': '2.0', 'data': data}
            require(len(dumps(wrapped).encode()) <= 131072, 'TOOL_RESULT_TOO_LARGE')
            return types.CallToolResult(content=[types.TextContent(type='text', text=dumps(wrapped))], structuredContent=wrapped)
        except DomainError as error:
            return types.CallToolResult(content=[types.TextContent(type='text', text=error.code)], isError=True)
    return Server('xueya-learning-platform', version='2.0.0', on_list_tools=list_tools, on_call_tool=call)


class PlatformSession:
    def __init__(self, client):
        self.client = client

    async def list_tools(self):
        return [{'name': t.name, 'description': t.description, 'inputSchema': t.input_schema} for t in (await self.client.list_tools()).tools]

    async def call(self, name, args=None):
        result = await self.client.call_tool(name, args or {})
        require(not result.is_error, result.content[0].text if result.content else 'MCP_TOOL_FAILED')
        wrapped = result.structured_content or json.loads(result.content[0].text)
        return wrapped['data'] if wrapped.get('schemaVersion') == '2.0' else wrapped


@asynccontextmanager
async def open_platform_session(platform, scope, timeout_ms=5000, library=None):
    global _active_sessions
    require(_active_sessions < 8, 'MCP_BUSY')
    _active_sessions += 1
    try:
        server = create_platform_server(platform, scope, library)
        async with asyncio.timeout(60), Client(server, read_timeout_seconds=timeout_ms/1000) as client:
            yield PlatformSession(client)
    finally:
        _active_sessions -= 1
