"""Plan resource metadata over existing fixed banks; never read RAG content."""
import ipaddress
from urllib.parse import quote, urlsplit
from .common import AppError, require
from .practice_bank import bank
from .practice_catalog import exam_bank


def question_catalog():
    result = []
    for source in (bank(), exam_bank()):
        for question in source['questions']:
            category = 'exam408' if question.get('bankSource') == 'exam408' else 'hot100' if question['category'] == 'hot100' else 'legacy'
            result.append({'type':'question', 'questionId':question['id'], 'version':source['version'],
                           'title':question.get('title') or question.get('topic') or question['prompt'][:100],
                           'subject':question.get('subject',''), 'topic':question.get('topic',''),
                           'tags':question.get('tags',[]), 'category':category, 'matched':True,
                           'url':'#space/practice/'+category+'/'+quote(question['id'],safe='')})
    return result


def external_link(url, title='用户补充学习资源'):
    require(isinstance(url,str) and 0 < len(url) <= 2048, 'INVALID_RESOURCE_URL')
    try:
        parsed=urlsplit(url)
        parsed.port
    except ValueError as error:
        raise AppError('INVALID_RESOURCE_URL') from error
    require(parsed.scheme in ('https','http') and parsed.hostname and not parsed.username and not parsed.password,
            'INVALID_RESOURCE_URL')
    require(not any(character in url for character in ('\n','\r','\x00','\\')), 'INVALID_RESOURCE_URL')
    try:
        require(ipaddress.ip_address(parsed.hostname).is_global, 'INVALID_RESOURCE_URL')
    except ValueError:
        require('.' in parsed.hostname and not parsed.hostname.endswith(('.localhost','.local')), 'INVALID_RESOURCE_URL')
    return {'type':'external','url':url,'title':str(title)[:200], 'matched':False,
            'sourceType':'user-link','verification':'unverified'}


def match_task(candidate):
    """Model suggestions cannot invent IDs. Ambiguous text remains self-study."""
    catalog=question_catalog()
    nested=candidate.get('resource') if isinstance(candidate.get('resource'),dict) else {}
    requested=candidate.get('questionId') or nested.get('questionId')
    if requested:
        resource=next((r for r in catalog if r['questionId']==requested),None)
        if resource:
            return dict(resource)
        return {'type':'self-study','matched':False,'reason':'资源不存在，按自主学习安排'}
    title=candidate.get('title','')
    matches=[]
    for resource in catalog:
        phrases=[resource['title'], resource['topic'], *resource['tags']]
        score=max((len(part) for part in phrases if isinstance(part,str) and len(part)>=3 and part in title),default=0)
        if score:
            matches.append((score,resource))
    matches.sort(key=lambda pair:pair[0],reverse=True)
    if matches and (len(matches)==1 or matches[0][0]>matches[1][0]):
        return dict(matches[0][1])
    return {'type':'self-study','matched':False}
