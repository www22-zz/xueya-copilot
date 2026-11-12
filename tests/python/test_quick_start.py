from urllib.parse import urlsplit, parse_qs
import pytest
import quick_start


def test_launcher_requests_dark_theme_without_changing_route(tmp_path, monkeypatch):
    monkeypatch.setattr(quick_start, 'ROOT', tmp_path)
    quick_start.save_target('http://127.0.0.1:43210/?existing=1#home')
    target = urlsplit((tmp_path / '.xueya-data/launch-url.txt').read_text())
    assert target.netloc == '127.0.0.1:43210'
    assert target.fragment == 'home'
    assert parse_qs(target.query) == {'existing': ['1'], 'theme': ['dark']}


def test_launcher_rejects_nonlocal_browser_target(tmp_path, monkeypatch):
    monkeypatch.setattr(quick_start, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='本机'):
        quick_start.save_target('https://example.com/')


def test_prepare_restores_browser_handler_after_host_failure(monkeypatch):
    original = quick_start.launch.webbrowser.open
    monkeypatch.setattr(quick_start.sys, 'argv', ['quick_start.py', '--prepare'])
    monkeypatch.setattr(quick_start.os, 'chdir', lambda _: None)
    def fail():
        raise RuntimeError('host failed')
    monkeypatch.setattr(quick_start.launch, 'main', fail)
    with pytest.raises(RuntimeError, match='host failed'):
        quick_start.main()
    assert quick_start.launch.webbrowser.open is original
