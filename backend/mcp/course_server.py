"""Real MCP stdio server; stdout is reserved for protocol messages."""
from typing import Any
from mcp.server.mcpserver import MCPServer as FastMCP
from ..rag import retrieve
from ..core import require, valid_date
from ..agent.tasks import local_study


def create_course_server():
    server = FastMCP('xueya-course-tools')

    def validate(sources):
        require(isinstance(sources, list) and len(sources) <= 48, 'INVALID_SOURCES')
        require(all(isinstance(s.get('id'), str) and 0 < len(s['id']) <= 150 and isinstance(s.get('quote'), str) and 0 < len(s['quote']) <= 1500 for s in sources), 'INVALID_SOURCES')

    @server.tool()
    def search_materials(query: str, sources: list[dict[str, Any]], limit: int = 4) -> dict:
        """检索本次请求提供的原文，只读。"""
        validate(sources)
        require(0 < len(query) <= 4000 and type(limit) is int and 1 <= limit <= 6, 'INVALID_QUERY')
        return {'sources': retrieve(query, sources)[:limit]}

    @server.tool()
    def read_source(sourceId: str, sources: list[dict[str, Any]]) -> dict:
        """按稳定来源 ID 读取本次请求原文，只读。"""
        validate(sources)
        source = next((s for s in sources if s['id'] == sourceId), None)
        require(source, 'SOURCE_NOT_FOUND')
        return {'source': source}

    def context(questions, records, baseDate):
        require(valid_date(baseDate) and len(questions) <= 100 and len(records) <= 120, 'INVALID_CONTEXT')
        known = {q['id'] for q in questions}
        return {'questions': questions, 'records': [r for r in records if r.get('questionId') in known and type(r.get('correct')) is bool], 'baseDate': baseDate}

    @server.tool()
    def analyze_progress(questions: list[dict[str, Any]], records: list[dict[str, Any]], baseDate: str) -> dict:
        """按实际作答统计薄弱知识点与到期复习，只读。"""
        return local_study(context(questions, records, baseDate), 'review')['progress']

    @server.tool()
    def build_review_plan(questions: list[dict[str, Any]], records: list[dict[str, Any]], baseDate: str, examDate: str, minutes: int) -> dict:
        """生成复习计划预览，不保存计划。"""
        require(valid_date(examDate) and examDate >= baseDate and questions and 15 <= minutes <= 120, 'INVALID_PLAN_SETTINGS')
        return local_study({**context(questions, records, baseDate), 'examDate': examDate, 'minutes': minutes}, 'plan')['plan']

    return server


if __name__ == '__main__':
    create_course_server().run(transport='stdio')
