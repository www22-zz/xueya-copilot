import pytest
from backend.xueya.objective_questions import grade, validate
from backend.xueya.common import AppError
from backend.xueya.study_space_service import StudySpaceService


@pytest.mark.parametrize('question,answer,correct', [
    ({'type':'single','options':['a','b'],'answer':0},0,True),
    ({'type':'multiple','options':['a','b','c'],'answer':[0,2]},[2,0],True),
    ({'type':'multiple','options':['a','b','c'],'answer':[0,2]},[0],False),
    ({'type':'boolean','answer':False},False,True),
    ({'type':'boolean','answer':False},True,False),
    ({'type':'fill','prompt':'____','answer':[['FIFO','先进先出']]},['先进先出'],True),
])
def test_deterministic_grade(question,answer,correct):
    assert grade(question,answer)['correct'] is correct


def test_fill_uncertain_not_zero():
    result=grade({'type':'fill','prompt':'____','answer':[['FIFO']]},['fifo'])
    assert result['status']=='pending-review'
    assert 'score' not in result and 'correct' not in result


@pytest.mark.parametrize('question,answer', [
    ({'type':'boolean','answer':True},1),
    ({'type':'multiple','options':['a','b'],'answer':[0,1]},[0,0]),
    ({'type':'fill','prompt':'____','answer':[['a']]},[]),
])
def test_invalid_answer_rejected(question,answer):
    with pytest.raises(AppError):grade(question,answer)


def test_fill_answers_never_projected():
    value=StudySpaceService.public_question({'id':'q','type':'fill','prompt':'____','answer':[['secret']]})
    assert value['blankCount']==1 and 'answer' not in value


def test_invalid_blank_count():
    with pytest.raises(AppError):validate({'type':'fill','prompt':'____ ____','answer':[['a']]})
