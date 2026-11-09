"""Run local checks with empty service credentials and fail-closed HTTP transport.

Usage: python -m scripts.check_isolated pytest -q [tests...]
       python -m scripts.check_isolated module scripts.check_learning_space_repair
"""
import ipaddress
import os
import runpy
import sys


def isolate():
    for key in ('MIMO_API_KEY', 'RAG_OCR_API_KEY', 'RAG_EMBEDDING_API_KEY',
                'RAG_RERANK_API_KEY', 'TAVILY_API_KEY', 'OPENAI_API_KEY'):
        os.environ[key] = ''
    os.environ['XUEYA_AUTO_IMPORT_DEMO'] = '0'
    os.environ['XUEYA_PRESERVE_LEGACY_DATA'] = '1'
    import httpx
    sync, asynchronous = httpx.HTTPTransport.handle_request, httpx.AsyncHTTPTransport.handle_async_request

    def allowed(request):
        host = request.url.host
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == 'localhost'
        if not local:
            raise AssertionError('UNMOCKED_EXTERNAL_HTTP_BLOCKED')

    def guarded(self, request):
        allowed(request)
        return sync(self, request)

    async def guarded_async(self, request):
        allowed(request)
        return await asynchronous(self, request)
    httpx.HTTPTransport.handle_request = guarded
    httpx.AsyncHTTPTransport.handle_async_request = guarded_async
    # The search adapter uses urllib; blank credentials alone must not be the
    # last line of defence if a fixture accidentally re-enables a service.
    import urllib.request
    from urllib.parse import urlsplit
    original_open = urllib.request.urlopen
    def guarded_open(url, *args, **kwargs):
        address = url.full_url if isinstance(url, urllib.request.Request) else str(url)
        host = urlsplit(address).hostname
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == 'localhost'
        if not local:
            raise AssertionError('UNMOCKED_EXTERNAL_HTTP_BLOCKED')
        return original_open(url, *args, **kwargs)
    urllib.request.urlopen = guarded_open


def main():
    isolate()
    mode, *args = sys.argv[1:]
    if mode == 'pytest':
        import pytest
        return pytest.main(args)
    if mode == 'module':
        module, *args = args
        sys.argv = [module, *args]
        runpy.run_module(module, run_name='__main__')
        return 0
    raise SystemExit('Expected pytest or module')


if __name__ == '__main__':
    raise SystemExit(main())
