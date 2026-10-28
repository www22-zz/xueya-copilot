"""Install and select a shared course curriculum without deleting personal practice history."""
import copy
import json

from backend.agent.data_structure_bank import PACKAGE_FILE, TEXTBOOK_HASH, validate_package
from .common import digest, require, utc_now

SELECTION = 'practice-curated-selection'
KIND = 'curated-practice-bank'


class CuratedPractice:
    def __init__(self, platform, rag):
        self.p, self.rag = platform, rag

    def preview(self, scope, package=None):
        package = validate_package(package or json.loads(PACKAGE_FILE.read_text(encoding='utf-8')))
        docs = [d for d in self.p.repo.all(scope, 'document') if d.get('fileHash') == TEXTBOOK_HASH
                and not d.get('archived') and not d.get('superseded')]
        require(len(docs) == 1, 'CURATED_TEXTBOOK_REQUIRED')
        doc = docs[0]
        sources = self.rag.sources(scope, document_ids=[doc['id']])
        require(sources, 'CURATED_TEXTBOOK_NOT_PARSED')
        questions = copy.deepcopy(package['questions'])
        for q in questions:
            ref = q['references'][0]
            same_page = [s for s in sources if s.get('page') == ref['page']]
            require(same_page, 'CURATED_REFERENCE_PAGE_UNAVAILABLE')
            # Bind to this installation's actual source IDs and exact stored text.
            source = max(same_page, key=lambda s: (ref['quote'] in s['quote'],
                sum(term in s['quote'] for term in q['tags']), len(s['quote'])))
            quote = ref['quote'] if ref['quote'] in source['quote'] else source['quote'][:240]
            q.update(courseId=scope.course_id, documentId=doc['id'], sourceId=source['id'],
                sourceVersion=str(doc['contentRevision']), evidenceQuote=quote, sourceLocation=source.get('location', ''))
        value = {'kind':KIND, 'packageId':package['id'], 'name':package['name'], 'contentHash':package['contentHash'],
            'documentId':doc['id'], 'documentRevision':doc['contentRevision'], 'units':package['units'],
            'questions':questions, 'createdAt':utc_now()}
        return value

    def install(self, scope, package=None):
        with self.p.db.transaction():
            value = self.preview(scope, package)
            entity_id = 'curated-' + value['packageId']
            prior = self.p.repo.read(scope, 'artifact', entity_id)
            if prior and prior['value']['contentHash'] == value['contentHash'] and prior['value']['documentRevision'] == value['documentRevision']:
                value = prior['value']
            else:
                self.p.repo.put(scope, 'artifact', entity_id, value)
            selection = self.p.repo.read(scope, 'artifact', SELECTION)
            desired = {'kind':SELECTION, 'packageId':value['packageId'], 'entityId':entity_id}
            if not selection or selection['value'] != desired:
                self.p.repo.put(scope, 'artifact', SELECTION, desired)
        return {'packageId':value['packageId'], 'name':value['name'], 'questions':len(value['questions']), 'units':len(value['units'])}

    def catalog(self, course_id=None, *, history=False):
        questions, summaries = [], []
        courses = self.p.repo.courses(self.p.user_id)
        for course in courses:
            if course_id and course['id'] != course_id or course['archived'] and not history:
                continue
            from .common import Scope
            scope = Scope(user_id=self.p.user_id, course_id=course['id'])
            selected = self.p.repo.read(scope, 'artifact', SELECTION)
            if history:
                values = [v for v in self.p.repo.all(scope, 'artifact') if v.get('kind') == KIND]
            else:
                row = self.p.repo.read(scope, 'artifact', selected['value']['entityId']) if selected else None
                values = [row['value']] if row else []
            for value in values:
                doc = self.p.repo.read(scope, 'document', value['documentId'])
                active = bool(doc and not doc['value'].get('archived') and not doc['value'].get('superseded')
                    and doc['value'].get('contentRevision') == value['documentRevision'])
                if history or active:
                    questions.extend(value['questions'])
                summaries.append({'id':value['packageId'], 'name':value['name'], 'status':'succeeded' if active else 'stale',
                    'courseId':course['id'], 'documentId':value['documentId'], 'completed':200, 'target':200,
                    'curated':True, 'units':value['units'], 'contentHash':value['contentHash']})
        return {'questions':questions, 'generations':summaries,
                'version':digest([[r['id'],r['courseId'],r['status'],r['contentHash']] for r in summaries])[:24]}
