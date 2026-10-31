"""Synthetic local evidence for the separately authorized real API smoke runner."""
from backend.xueya.common import utc_now
from backend.xueya.course_records import CourseRecords,platform_courses
from backend.xueya.study_space_service import StudySpaceService


def seed(platform,account):
    course=platform_courses()[0]
    CourseRecords(platform).record(account,{'courseId':course['id'],'episodeId':course['episodes'][0]['id'],'completed':True,'operationId':'synthetic-course'})
    scope=StudySpaceService(platform)._scope(account)
    evaluation={'id':'synthetic-evaluation','source':'human','status':'graded','createdAt':utc_now(),
        'result':{'feedback':'合成样例的人工观察：说明了互斥，但没有说明有限等待。','score':2,'maxScore':4}}
    platform.repo.put(scope,'attempt','synthetic-attempt',{'id':'synthetic-attempt','questionId':'synthetic-question','createdAt':utc_now(),
        'answer':'临界区同一时刻最多允许一个进程进入。','questionSnapshot':{'id':'synthetic-question','type':'short','prompt':'说明临界区互斥的基本含义。'},
        'evaluations':[evaluation],'effectiveEvaluation':evaluation,'revision':1},0)
