"""F independent acceptance fixtures, strict evidence metrics and a full durable loop."""
import asyncio
from datetime import date, timedelta

from fastapi.testclient import TestClient
from backend.xueya.app import create_app
from backend.xueya.backup import create_backup, restore_backup
from backend.xueya.config import Config
from backend.xueya.rag import parse_document
from backend.xueya.rag_eval import finish
from scripts.build_quality_materials import build
from scripts.check_quality import score_case


def test_original_material_formats_do_not_invent_scan_text(tmp_path):
    value = build(tmp_path/'materials')
    assert len(value['cases']) == 60 and sum(c['split'] == 'test' for c in value['cases']) == 46
    original = parse_document((tmp_path/'materials/structures.md').read_bytes(), 'md')
    assert {'table', 'code', 'formula'} <= {b['type'] for b in original['blocks']}
    docx = parse_document((tmp_path/'materials/lecture.docx').read_bytes(), 'docx')
    assert 'Queue' in docx['text'] and 'FIFO' in docx['text']
    assert 'first in, first out' in parse_document((tmp_path/'materials/lecture.pdf').read_bytes(), 'pdf')['text']
    scan = parse_document((tmp_path/'materials/scan-only.pdf').read_bytes(), 'pdf')
    assert not scan['text'].strip() and scan['pages'][0]['needsOcr']
    long = parse_document((tmp_path/'materials/long-chapter.md').read_bytes(), 'md')
    assert 'END_MARKER_40' in long['text']


def test_multiple_gold_evidence_requires_both_documents():
    case = {'gold': [{'document': 'a', 'quote': '正面声明'}, {'document': 'b', 'quote': '相反声明'}]}
    ids = {'a': 'a-id', 'b': 'b-id'}
    one = score_case(case, [{'documentId': 'a-id', 'quote': '正面声明'}], ids)
    assert not one['passed'] and one['matchedGold'] == 1
    assert score_case(case, [{'documentId': 'a-id', 'quote': '正面声明'}, {'documentId': 'b-id', 'quote': '相反声明'}], ids)['passed']
    assert not score_case({'gold': []}, [{'documentId': 'a-id', 'quote': '无关命中'}], ids)['passed']
