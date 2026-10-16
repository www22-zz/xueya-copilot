import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config(root=ROOT):
    env = dict(os.environ)
    file = Path(root) / '.env'
    if file.exists():
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                env.setdefault(name.strip(), value.strip().strip('\"\''))
    return {'root': Path(root), 'port': int(env.get('PORT', '4173')),
            'platform': {'enabled': True, 'dataDir': Path(env.get('XUEYA_DATA_DIR', Path(root)/'.xueya-data')).resolve(), 'userId': 'local-user', 'apiSlots': max(1, min(8, int(env.get('API_MAX_CONCURRENT', '2'))))},
            'agent': {'toolTimeoutMs': max(1000, min(10000, int(env.get('MCP_TOOL_TIMEOUT_MS', '5000'))))},
            'ai': {'apiKey': env.get('MIMO_API_KEY', ''),
                   'baseURL': env.get('MIMO_BASE_URL', 'https://api.xiaomimimo.com/v1'),
                   'model': env.get('MIMO_MODEL', 'mimo-v2.6-flash')}}
