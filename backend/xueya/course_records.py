"""Account-owned video metadata, explicit completion and resumable positions.

Uses the platform Repository/SQLite. A playback position is never mastery or a
completion event; only explicit user confirmation can complete a course task.
"""
import copy
import json
import re
from pathlib import Path
from urllib.parse import quote

from .common import digest, identifier, require, utc_now


def platform_courses():
    return json.loads((Path(__file__).resolve().parents[2] / 'frontend/data/video-courses.json').read_text(encoding='utf-8'))


class CourseRecords:
    def __init__(self, platform):
        from .study_space_service import StudySpaceService
        self.p = platform
        self.space = StudySpaceService(platform)

    def scope(self, account):
        return self.space._scope(account)

    def listing(self, account):
        scope = self.scope(account)
        private = [r for r in self.p.repo.all(scope, 'artifact') if r.get('kind') == 'video-course']
        progress = {}
        for r in self.p.repo.all(scope, 'artifact'):
            if r.get('kind') != 'video-progress':
                continue
            course = progress.setdefault(r['courseId'], {'episodes': {}})
            course['episodes'][r['episodeId']] = r
            if r['updatedAt'] >= course.get('updatedAt', ''):
                course.update(lastEpisodeId=r['episodeId'], updatedAt=r['updatedAt'])
        return {'courses': platform_courses() + private, 'progress': progress}

    def course(self, account, course_id):
        return next((c for c in self.listing(account)['courses'] if c['id'] == course_id), None)

    def episode(self, account, course_id, episode_id):
        course = self.course(account, course_id)
        require(course is not None, 'COURSE_NOT_FOUND')
        episode = next((e for e in course['episodes'] if e['id'] == episode_id), None)
        require(episode is not None, 'EPISODE_NOT_FOUND')
        return course, episode

    def operation(self, account, data, action, function):
        scope = self.scope(account)
        key = 'course-operation-' + digest(identifier(data.get('operationId')))[:40]
        signature = digest({'action': action, 'request': data})
        with self.p.db.transaction():
            row = self.p.repo.read(scope, 'artifact', key)
            if row:
                require(row['value']['signature'] == signature, 'IDEMPOTENCY_CONFLICT')
                return copy.deepcopy(row['value']['result'])
            result = function()
            self.p.repo.put(scope, 'artifact', key, {'kind': 'course-operation', 'signature': signature, 'result': result}, 0)
            return result

    def save_course(self, account, data):
        def save():
            course = data.get('course')
            require(isinstance(course, dict), 'INVALID_COURSE')
            course = copy.deepcopy(course)
            course_id = identifier(course.get('id'))
            require(course_id.startswith('custom-'), 'PLATFORM_COURSE_READONLY')
            require(isinstance(course.get('title'), str) and 0 < len(course['title']) <= 200, 'INVALID_COURSE')
            episodes = course.get('episodes')
            require(isinstance(episodes, list) and 1 <= len(episodes) <= 100, 'INVALID_COURSE')
            ids = set()
            for ep in episodes:
                require(isinstance(ep, dict), 'INVALID_EPISODE')
                ep_id = identifier(ep.get('id'))
                require(ep_id not in ids and isinstance(ep.get('title'), str) and 0 < len(ep['title']) <= 200, 'INVALID_EPISODE')
                ids.add(ep_id)
                bvid = ep.get('bvid') or course.get('bvid')
                video = ep.get('videoUrl')
                require((isinstance(bvid, str) and re.fullmatch(r'BV[0-9A-Za-z]{10}', bvid)) or video, 'INVALID_VIDEO_SOURCE')
                if video:
                    from .study_resources import external_link
                    external_link(video)
                require(type(ep.get('bpage', 1)) is int and 1 <= ep.get('bpage', 1) <= 10000, 'INVALID_EPISODE')
            # Accept only display metadata; never persist client ownership or grading fields.
            allowed = ('id','title','category','categoryName','level','badge','instructor','duration','bvid','description','tags','episodes','coverGradient','coverIcon')
            course = {k: v for k, v in course.items() if k in allowed}
            course.update(kind='video-course', platform=False, sourceType='private', verification='user-unverified', updatedAt=utc_now())
            scope = self.scope(account)
            row = self.p.repo.read(scope, 'artifact', course_id)
            expected = data.get('expectedRevision', 0)
            require(type(expected) is int and expected == (row['value']['revision'] if row else 0), 'COURSE_REVISION_CONFLICT')
            course['revision'] = expected + 1
            self.p.repo.put(scope, 'artifact', course_id, course, row['version'] if row else 0)
            return {'course': course}
        return self.operation(account, data, 'save-course', save)

    def record(self, account, data, *, from_plan=False):
        def save():
            course, episode = self.episode(account, data.get('courseId'), data.get('episodeId'))
            scope = self.scope(account)
            key = 'video-progress-' + digest([course['id'], episode['id']])[:40]
            row = self.p.repo.read(scope, 'artifact', key)
            prior = row['value'] if row else {}
            if 'expectedRevision' in data:
                require(type(data['expectedRevision']) is int and data['expectedRevision'] == prior.get('revision', 0), 'COURSE_REVISION_CONFLICT')
            value = {**prior, 'kind':'video-progress', 'id':key, 'courseId':course['id'], 'episodeId':episode['id']}
            if 'completed' in data:
                require(type(data['completed']) is bool, 'INVALID_COURSE_STATUS')
                value.update(completed=data['completed'], completionSource='plan-confirmation' if from_plan else 'manual-confirmation')
            if 'seconds' in data:
                seconds = data['seconds']
                require(type(seconds) in (int, float) and 0 <= seconds <= 1000000, 'INVALID_VIDEO_POSITION')
                require(data.get('positionSource') in ('html5-observed', 'user-position'), 'INVALID_VIDEO_POSITION')
                value.update(seconds=round(seconds), positionSource=data['positionSource'])
            changed = any(value.get(k) != prior.get(k) for k in ('completed','seconds','positionSource'))
            value.setdefault('completed', False)
            if changed or not row:
                value.update(revision=prior.get('revision', 0) + 1, updatedAt=utc_now())
                self.p.repo.put(scope, 'artifact', key, value, row['version'] if row else 0)
                if 'completed' in data and value['completed'] != prior.get('completed', False):
                    event_id = 'course-event-' + digest([key, value['revision']])[:40]
                    self.p.repo.put(scope, 'event', event_id, {'id':event_id,'source':'course','action':'completion',
                        'courseId':course['id'],'episodeId':episode['id'],'completed':value['completed'],
                        'completionSource':value['completionSource'],'at':value['updatedAt']}, 0)
            synced = 0 if from_plan or 'completed' not in data else self.space.sync_course_completion(account, course['id'], episode['id'], value['completed'])
            return {'progress':value,'syncedTasks':synced}
        return save() if from_plan else self.operation(account, data, 'progress', save)

    def continue_learning(self, account):
        data = self.listing(account)
        available={c['id']:{e['id'] for e in c['episodes']} for c in data['courses']}
        latest = max((e for c in data['progress'].values() for e in c['episodes'].values()
                      if e['episodeId'] in available.get(e['courseId'],set())), key=lambda e:e['updatedAt'], default=None)
        if not latest:
            return None
        course, episode = self.episode(account, latest['courseId'], latest['episodeId'])
        return {'courseId':course['id'],'episodeId':episode['id'],'title':course['title']+' · '+episode['title'],
                'url':'#space/courses/'+quote(course['id'],safe='')+'/'+quote(episode['id'],safe=''),
                'seconds':latest.get('seconds'), 'positionSource':latest.get('positionSource'), 'completed':latest['completed']}

    def delete_course(self, account, data):
        def delete():
            scope=self.scope(account)
            row=self.p.repo.read(scope,'artifact',identifier(data.get('courseId')))
            require(row and row['value'].get('kind')=='video-course','COURSE_NOT_FOUND')
            require(type(data.get('expectedRevision')) is int and data['expectedRevision']==row['value']['revision'],'COURSE_REVISION_CONFLICT')
            self.p.repo.put(scope,'artifact',row['id'],row['value'],row['version'],deleted=True)
            return {'deleted':True,'courseId':row['id']}
        return self.operation(account,data,'delete-course',delete)
