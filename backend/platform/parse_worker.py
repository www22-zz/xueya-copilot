"""Isolated cancellable parser. Only stdin/stdout JSON; no model or filesystem scope."""
import base64
import json
import sys
from ..rag import parse_document, extract_chunks
from ..core import require, dumps


def main():
    value = json.loads(sys.stdin.buffer.read(16000000))
    binary = base64.b64decode(value['data'], validate=True)
    require(len(binary) <= 10485760, 'FILE_TOO_LARGE')
    kind = value['kind']
    if kind in ('txt', 'md'):
        require(len(binary) <= 1048576, 'FILE_TOO_LARGE')
        text = binary.decode('utf-8-sig')[:120000]
    else:
        text = parse_document(binary, kind)['text']
    result = {'sources': extract_chunks(text, value['document'])}
    sys.stdout.buffer.write(dumps(result).encode())


if __name__ == '__main__':
    main()
