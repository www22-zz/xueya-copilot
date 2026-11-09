from backend.xueya.material_learning import MaterialLearning
from backend.xueya.study_space_service import StudySpaceService


def test_material_framework_discloses_unrepresented_phases_and_task_splits(platform):
    service=StudySpaceService(platform);scope=service._scope('coverage-owner')
    platform.repo.put(scope,'artifact','m',{'concepts':[{'id':'k','label':'队列','questionIds':['q']}]},0)
    resource={'type':'question','conceptId':'k','materialId':'m','questionId':'q'}
    plan={'id':'p','title':'阶段计划','subjects':['数据结构'],'goal':'学习队列','days':[
        {'date':'2026-11-05','tasks':[{'id':'t1','sourceTaskId':'source-1','phase':'基础','resource':resource}]},
        {'date':'2026-11-06','tasks':[{'id':'t2','sourceTaskId':'source-1','phase':'基础','resource':resource},
                                   {'id':'t3','sourceTaskId':'source-2','phase':'应用','resource':{'type':'course'}}]}]}
    material=object.__new__(MaterialLearning);material.p=platform;material.service=service
    framework=material.plan_framework('coverage-owner',plan)
    assert framework['coverage']=={'kind':'material-linked','totalPhases':2,'representedPhases':1,
                                   'totalTasks':2,'representedTasks':1,'partial':True}
    assert len([n for n in framework['nodes'] if n.get('conceptId')])==1
    assert '资料关联' in framework['title']
