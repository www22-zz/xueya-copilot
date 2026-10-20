def test_chapter_note_save_edit_history_and_scope(client):
    headers=client.platform_headers
    def call(path,value=None):
        r=client.get('/api/learning/'+path,headers=headers) if value is None else client.post('/api/learning/'+path,json=value,headers=headers)
        assert r.status_code==200,r.text
        return r.json()['result']
    first=call('content/note/preview',{'id':'chapter-note','title':'栈','text':'后进先出','chapter':'第25章 栈','expectedRevision':0})
    saved=call('draft/adopt',{'draftId':first['draftId'],'operationId':'save-note','confirmed':True})
    assert saved['content']['chapter']=='第25章 栈'
    revised=call('content/note/preview',{'id':'chapter-note','title':'栈','text':'后进先出；补充例子','expectedRevision':1})
    result=call('draft/adopt',{'draftId':revised['draftId'],'operationId':'edit-note','confirmed':True})
    assert result['revision']==2 and result['content']['chapter']=='第25章 栈'
    assert call('artifacts?id=chapter-note')['content']['text'].endswith('补充例子')
    conflict=client.post('/api/learning/content/note/preview',json={'id':'chapter-note','text':'旧版本','chapter':'另一章','expectedRevision':1},headers=headers)
    assert conflict.status_code==409
    invalid=client.post('/api/learning/content/note/preview',json={'id':'bad-chapter','text':'x','chapter':'a'*201,'expectedRevision':0},headers=headers)
    assert invalid.status_code==400
    client.platform.repo.ensure_course(client.platform.user_id,{'id':'other','name':'Other'})
    assert client.get('/api/learning/artifacts?courseId=other&id=chapter-note',headers=headers).status_code==404
    assert not client.platform.db.all('SELECT * FROM invocations')
