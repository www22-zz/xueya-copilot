"""Read-only chapter nodes from the current parser-validated Markdown sources."""
import re
from .common import digest


def markdown_outline(document_id, sources):
    groups = {}
    for source in sorted(sources, key=lambda s: s.get('start', 0)):
        path = source.get('sectionPath') or []
        # The first heading names the document; its immediate sections form
        # the third graph layer. Nested paragraphs remain in their section.
        if len(path) < 2:
            continue
        section = path[1]
        group = groups.setdefault(section, {'sources': [], 'paragraphs': []})
        group['sources'].append(source)
        text = re.sub(r'<!--.*?-->', '', source.get('quote', ''), flags=re.S).strip()
        if text and not text.startswith(('#', '```', '~~~', '|')):
            group['paragraphs'].append(text)
    nodes = []
    for section, group in groups.items():
        # Keep the source heading in the reference; hide only its local index.
        label = re.sub(r'^[A-Z]{1,8}\d+(?:\.\d+)*\s+', '', section).strip()
        key = 'outline-' + digest([document_id, section])[:40]
        nodes.append({'id': key, 'label': label or section, 'kind': 'concept',
                      'sourceType': 'markdown-outline', 'questionIds': [],
                      'descriptions': ['\n\n'.join(group['paragraphs'])[:1800] or '本节点来自资料中的章节标题。'],
                      'references': [{'documentId': document_id, 'sourceId': s['id'],
                                      'page': s.get('page'), 'sectionPath': s.get('sectionPath', [])}
                                     for s in group['sources'][:3]]})
    return nodes
