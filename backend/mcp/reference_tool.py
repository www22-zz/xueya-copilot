import re
from urllib.parse import quote
import httpx
from ..core import require, DomainError


async def lookup_reference(doi, *, enabled=False, transport=None):
    """Only DOI public metadata is sent; never course text, API keys or arbitrary URLs."""
    require(enabled, 'REFERENCE_DISABLED')
    require(isinstance(doi, str) and len(doi) <= 200 and re.fullmatch(r'10\.\d{4,9}/[!-~]+', doi), 'INVALID_REFERENCE')
    async with httpx.AsyncClient(transport=transport, timeout=5, follow_redirects=False) as client:
        async with client.stream('GET', 'https://api.crossref.org/works/'+quote(doi, safe=''), headers={'Accept': 'application/json', 'User-Agent': 'Xueya-Copilot/2.0 (learning-reference-lookup)'}) as response:
            require(response.status_code != 404, 'REFERENCE_NOT_FOUND')
            require(response.is_success, 'REFERENCE_UNAVAILABLE')
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                require(len(data) <= 262144, 'REFERENCE_TOO_LARGE')
    import json
    try:
        message = json.loads(data)['message']
        require(isinstance(message.get('DOI'), str) and message['DOI'].lower() == doi.lower(), 'INVALID_REFERENCE')
        return {'doi': message['DOI'], 'title': str((message.get('title') or [''])[0])[:500], 'publisher': str(message.get('publisher', ''))[:300],
                'year': (message.get('published', {}).get('date-parts') or [[None]])[0][0], 'url': 'https://doi.org/'+quote(message['DOI'], safe=''), 'source': 'Crossref public metadata', 'courseEvidence': False}
    except (KeyError, TypeError, ValueError):
        raise DomainError('INVALID_REFERENCE') from None
