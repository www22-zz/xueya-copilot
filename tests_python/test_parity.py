"""Outputs captured from the real pre-migration JS implementation, not Python mirrors."""
import json
from pathlib import Path
import pytest
from backend.agent.planning import plan_study
from backend.agent.study import mastery
from backend.agent.study_session import build_study_session
from backend.agent.question_service import select_practice

REFERENCE = json.loads((Path(__file__).parent/'fixtures/js-parity.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', REFERENCE['plans'])
def test_calendar_port_matches_existing_javascript_outputs(course, case):
    result = plan_study({**course, **case['setting']})
    assert {key: result[key] for key in case['expected']} == case['expected']


def test_mastery_recommendations_and_practice_match_javascript(course):
    estimates = mastery(course['events'], {'courseId': course['courseId'], 'baseDate': course['baseDate']})
    assert estimates == REFERENCE['mastery']
    session = build_study_session(course)
    assert session['daily'] == REFERENCE['daily']
    practice = select_practice(course['questions'], {'courseId': course['courseId'], 'count': 3, 'estimates': session['estimates'], 'recentQuestionIds': [e['questionId'] for e in course['events']]})
    assert practice == REFERENCE['practice']
