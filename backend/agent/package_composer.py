from ..core import check_cancel, fingerprint
from .study_session import build_study_session
from .assessment import assemble_quiz


async def compose_package(content, value, **options):
    check_cancel(options.get('signal'))
    study = build_study_session(value)
    summary = await content.summarize(value, **options)
    quiz = assemble_quiz([item['question'] for item in study['practice']['items']], {'courseId': value['courseId'], 'count': value.get('practiceCount', 5)})
    check_cancel(options.get('signal'))
    exercises = [{'id': 'self-check-'+str(i), 'type': 'self-explanation', 'prompt': '用自己的话解释这段原文，并核对出处。', 'reference': c['text'] if c['support'] == 'supported' else '\n'.join(r['quote'] for r in c['evidence']), 'evidence': c['evidence'], 'status': 'self-check' if c['support'] == 'supported' else 'needs-review'} for i, c in enumerate(summary['claims'])]
    return {'kind': 'learning-package', 'courseId': value['courseId'], 'summary': summary, 'exercises': exercises, 'quiz': quiz, 'coreConcepts': study['path']['entries'],
            'weakPoints': {'estimates': study['estimates'], 'diagnosticActions': study['diagnosticActions']}, 'recommendations': study['daily']['items'], 'plan': study['plan'], 'studyVersion': study['version'], 'evidenceVersion': summary['evidenceVersion'],
            'version': fingerprint({'studyVersion': study['version'], 'summary': summary, 'quiz': quiz['version'], 'plan': study['plan']}), 'gaps': study['warnings']+(['APPROVED_QUESTION_SHORTFALL'] if not quiz['complete'] else [])+(['NO_CURATED_CONCEPTS'] if not study['path']['entries'] else []),
            'adoption': 'preview', 'requiresConfirmation': True, 'planAdoption': 'separate-preview-required'}
