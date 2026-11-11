import os
import pytest

from backend.xueya.rag_http import configured_service


def prepare(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith(('RAG_', 'XUEYA_SHARED_EMBEDDING')):
            monkeypatch.delenv(key)
    (tmp_path / '.env.team-embedding').write_text(
        'RAG_EMBEDDING_API_KEY=synthetic-team-key\n'
        'RAG_EMBEDDING_PROVIDER=moark-qwen\n'
        'RAG_EMBEDDING_MODEL=Qwen3-VL-Embedding-2B\n'
        'RAG_EMBEDDING_BASE_URL=https://api.moark.com/v1\n'
        'RAG_EMBEDDING_DIMENSION=2048\n'
        'RAG_RERANK_API_KEY=must-not-load\nRAG_RERANK_MODEL=ignored\n', encoding='utf-8')


@pytest.mark.parametrize('local', [None, 'RAG_EMBEDDING_API_KEY=\nRAG_EMBEDDING_PROVIDER=jina\nRAG_EMBEDDING_DIMENSION=1024\n'])
def test_fresh_checkout_and_blank_local_template_use_shared_provider(platform, tmp_path, monkeypatch, local):
    prepare(monkeypatch, tmp_path)
    if local is not None:
        (tmp_path / '.env').write_text(local, encoding='utf-8')
    rag = configured_service(platform, tmp_path)
    assert rag.embedding.settings.key == 'synthetic-team-key'
    assert rag.embedding.identity['model'] == 'Qwen3-VL-Embedding-2B'
    assert rag.embedding.identity['dimension'] == 2048
    assert rag.rerank is None and rag.ocr is None
    assert not platform.db.one('SELECT id FROM invocations')


@pytest.mark.parametrize('override', ['local', 'environment', 'disabled'])
def test_own_config_and_environment_override_shared_and_can_disable(platform, tmp_path, monkeypatch, override):
    prepare(monkeypatch, tmp_path)
    (tmp_path / '.env').write_text('RAG_EMBEDDING_API_KEY=own-key\nRAG_EMBEDDING_MODEL=own-model\n', encoding='utf-8')
    if override == 'environment':
        monkeypatch.setenv('RAG_EMBEDDING_API_KEY', 'environment-key')
    elif override == 'disabled':
        monkeypatch.setenv('RAG_EMBEDDING_API_KEY', '')
        monkeypatch.setenv('XUEYA_SHARED_EMBEDDING', '0')
    rag = configured_service(platform, tmp_path)
    if override == 'disabled':
        assert rag.embedding is None
    else:
        assert rag.embedding.settings.key == ('environment-key' if override == 'environment' else 'own-key')
        assert rag.embedding.settings.model == 'own-model'
