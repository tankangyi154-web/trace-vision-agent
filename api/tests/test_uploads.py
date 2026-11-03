import json
import time
from pathlib import Path
import pytest


def test_upload_limits_do_not_accept_unbounded_or_unsupported_inputs():
    from api.uploads import validate_upload, UploadError
    assert validate_upload('我的照片.PNG',1000)=='image'
    assert validate_upload('clip.mp4',1024)=='video'
    assert validate_upload('phone.jpg',20*1024*1024)=='image'
    assert validate_upload('clip.mp4',200*1024*1024)=='video'
    for filename,size in [('x.svg',10),('x.jpg',20*1024*1024+1),('x.mp4',200*1024*1024+1),('x.jpg',0)]:
        with pytest.raises(UploadError): validate_upload(filename,size)


def test_clean_preview_uses_the_same_private_token_allowlist_as_annotations(tmp_path):
    from api.uploads import UploadService,UploadError
    service=UploadService(tmp_path/'jobs')
    public=service.reserve('owner','clip.mp4',100,classes=[0,2])
    job=service._read(public['id']);directory=service._path(public['id'])
    result={'kind':'video','media':'r1-annotated.webm','poster':'poster.jpg','source_media':'analysis-source.mp4','evidence':[],'highlights':[]}
    for name in ('r1-annotated.webm','poster.jpg','analysis-source.mp4','source.mp4'):(directory/name).write_bytes(b'fixture')
    job.update(status='complete',result=result);service._write(job)
    assert service.asset(job['id'],'analysis-source.mp4',job['asset_token']).name=='analysis-source.mp4'
    assert 'token=' in service.get(job['id'],'owner')['result']['annotation_source_url']
    with pytest.raises(UploadError):service.asset(job['id'],'analysis-source.mp4','wrong-token')
    with pytest.raises(UploadError):service.asset(job['id'],'source.mp4',job['asset_token'])
    with pytest.raises(UploadError):service.get(job['id'],'another-owner')


def test_http_upload_header_allows_larger_files_but_checks_received_bytes(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from api.index import create_app
    from api.config import Settings
    from api.store import SQLiteStore
    from api.uploads import UploadService
    monkeypatch.setattr(UploadService,'available',lambda self:True)
    monkeypatch.setattr(UploadService,'__init__',_isolated_service_init(tmp_path,UploadService.__init__))
    client=TestClient(create_app(Settings(),SQLiteStore(tmp_path/'http.db')))
    sid=client.post('/api/sessions').json()['session_id']
    headers={'X-Session-ID':sid,'X-Filename':'clip.mp4','X-File-Size':str(200*1024*1024),
             'X-Target-Classes':'[2]','Content-Type':'application/octet-stream'}
    # A declared 200 MiB video reaches the actual stream-length check, beyond the old 30 MiB header cap.
    result=client.post('/api/uploads',headers=headers,content=b'not-the-declared-size')
    assert result.status_code==422 and result.json()['detail']['code']=='decode'
    headers['X-Filename']='photo.jpg';headers['X-File-Size']=str(20*1024*1024+1)
    result=client.post('/api/uploads',headers=headers,content=b'')
    assert result.status_code==413 and result.json()['detail']['code']=='size'
    headers['X-Filename']='clip.mp4';headers['X-File-Size']=str(200*1024*1024+1)
    assert client.post('/api/uploads',headers=headers,content=b'').status_code==422
    assert not list((tmp_path/'uploads').glob('*/job.json'))


def _isolated_service_init(tmp_path,original):
    def initialize(self,*args,**kwargs):
        kwargs['directory']=tmp_path/'uploads'
        original(self,*args,**kwargs)
    return initialize


def test_long_media_request_is_not_marked_unknown_at_the_short_text_agent_timeout(tmp_path):
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from api.index import create_app
    from api.config import Settings
    from api.store import SQLiteStore
    store=SQLiteStore(tmp_path/'long-request.db')
    sid=store.create_session();ids=[]
    for scene in ('upload-'+str(uuid4()),'harbor'):
        rid=str(uuid4());ids.append(rid)
        store.reserve(sid,rid,rid,{'scene_id':scene},'day',5,50)
        store.update(sid,rid,{'created_at':time.time()-200,'status':'running'})
    client=TestClient(create_app(Settings(),store))
    media=client.get('/api/requests/'+ids[0],headers={'X-Session-ID':sid}).json()
    text=client.get('/api/requests/'+ids[1],headers={'X-Session-ID':sid}).json()
    assert media['status']=='running'
    assert text['status']=='failed' and text['error']['code']=='execution_unknown'


def test_selected_classes_are_bound_to_the_private_job_and_limited(tmp_path):
    from api.uploads import UploadService,UploadError
    service=UploadService(directory=tmp_path/'uploads')
    job=service.reserve('owner','image.jpg',100,classes=[0,2,16])
    restored=service.get(job['id'],'owner')
    assert restored['classes']==[0,2,16] and restored['class_names']==['人','汽车','狗']
    for classes in ([0,1,2,3],[2,2],[80],[False],['car']):
        with pytest.raises(UploadError):service.reserve('owner','image.jpg',100,classes=classes)
    service.delete(job['id'],'owner');service.close()


def test_private_job_owner_expiry_and_delete_stay_inside_temporary_root(tmp_path):
    from api.uploads import UploadService,UploadError
    service=UploadService(directory=tmp_path/'uploads',enabled=True)
    job=service.reserve('owner-a','pic.jpg',100,classes=[2])
    job_id=job['id']; directory=service.directory/job_id
    (directory/'source.jpg').write_bytes(b'temporary')
    with pytest.raises(UploadError):service.get(job_id,'owner-b')
    with pytest.raises(UploadError):service.get('../outside','owner-a')
    sentinel=tmp_path/'keep.txt';sentinel.write_text('keep')
    service.delete(job_id,'owner-a')
    assert not directory.exists() and sentinel.read_text()=='keep'
    old=service.reserve('owner-a','old.jpg',100,classes=[2])
    record=service.directory/old['id']/'job.json'
    data=json.loads(record.read_text());data.update(status='complete',expires_at=time.time()-1);record.write_text(json.dumps(data))
    service.cleanup()
    assert not record.exists()


def test_delete_removes_only_that_uploads_chat_records_without_refunding_model_quota(tmp_path):
    from api.store import SQLiteStore,StoreError
    from uuid import uuid4
    store=SQLiteStore(tmp_path/'private.sqlite3');sid=store.create_session()
    one='upload-'+str(uuid4());two='upload-'+str(uuid4())
    ids=[]
    for scene in (one,two):
        rid=str(uuid4());ids.append(rid)
        store.reserve(sid,rid,rid,{'scene_id':scene},'test-day',5,50)
        store.finish(sid,rid,{'status':'complete','answer':'本次结果','citations':[{'evidence_id':scene+'-e0'}]},scene+':A:3','问题')
    store.forget_media(one)
    with pytest.raises(StoreError):store.get_request(sid,ids[0])
    assert store.history(sid,one+':A:3')==[]
    assert store.get_request(sid,ids[1])['answer']=='本次结果'
    assert store.remaining(sid,5)==3


def test_forget_cannot_be_undone_by_a_finish_that_was_already_in_flight(tmp_path,monkeypatch):
    import threading
    from uuid import uuid4
    from api.store import SQLiteStore,StoreError
    store=SQLiteStore(tmp_path/'race.sqlite3');sid=store.create_session();scene='upload-'+str(uuid4());rid=str(uuid4())
    store.reserve(sid,rid,rid,{'scene_id':scene},'day',5,50)
    committed=threading.Event();resume=threading.Event();errors=[];connect=store.connect
    class PauseAfterCommit:
        def __init__(self):self.c=connect()
        def __getattr__(self,name):return getattr(self.c,name)
        def __enter__(self):self.c.__enter__();return self
        def __exit__(self,*args):return self.c.__exit__(*args)
        def commit(self):self.c.commit();committed.set();assert resume.wait(3)
    monkeypatch.setattr(store,'connect',lambda:PauseAfterCommit() if threading.current_thread().name=='finishing' else connect())
    def finish():
        try:store.finish(sid,rid,{'status':'complete','answer':'private answer'},scene+':A:3','private question')
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=finish,name='finishing');thread.start()
    assert committed.wait(3)
    try:store.forget_media(scene)
    finally:resume.set();thread.join(3)
    assert not thread.is_alive() and not errors
    assert store.history(sid,scene+':A:3')==[]
    with pytest.raises(StoreError):store.get_request(sid,rid)


def _completed_record(service,owner,filename):
    public=service.reserve(owner,filename,100,classes=[0,2])
    job=service._read(public['id'])
    job.update(status='complete',expires_at=time.time()-1,result={'kind':'video','media':'annotated.webm',
        'poster':'poster.jpg','source_media':'analysis-source.mp4','evidence':[],'highlights':[],
        'duration':40,'targets':[],'counts':[]})
    for name in ('annotated.webm','poster.jpg','analysis-source.mp4'):(service._path(job['id'])/name).write_bytes(b'fixture')
    service._write(job)
    return job


def test_completed_local_records_survive_cleanup_restart_and_are_owner_scoped(tmp_path):
    from api.uploads import UploadService,UploadError
    directory=tmp_path/'jobs';service=UploadService(directory)
    one=_completed_record(service,'owner-a','one.mp4');two=_completed_record(service,'owner-b','two.mp4')
    service.cleanup();service.close();service=UploadService(directory)
    assert service.get(one['id'],'owner-a')['expires_at'] is None
    assert [r['id'] for r in service.records('owner-a')]==[one['id']]
    assert service.records('unknown')==[]
    with pytest.raises(UploadError):service.delete(two['id'],'owner-a')
    service.delete(one['id'],'owner-a')
    assert service.records('owner-a')==[] and len(service.records('owner-b'))==1
    service.close()


def test_saved_media_access_is_separate_from_question_session_and_keeps_quota(tmp_path,monkeypatch):
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from api.index import create_app
    from api.config import Settings
    from api.store import SQLiteStore
    from api.uploads import UploadService
    directory=tmp_path/'uploads';service=UploadService(directory);store=SQLiteStore(tmp_path/'records.db')
    old_owner=store.create_session();new_session=store.create_session()
    record=_completed_record(service,old_owner,'saved.mp4');service.close()
    monkeypatch.setattr(UploadService,'__init__',_isolated_service_init(tmp_path,UploadService.__init__))
    async def agent(*args,**kwargs):
        return {'answer':'已读取保存的结果。','citations':[],'rule_citations':[],
                'tool_calls':[],'usage':{'model_calls':1,'tool_calls':0,'input_tokens':1,'output_tokens':1}}
    monkeypatch.setattr('api.index.run_agent',agent)
    with TestClient(create_app(Settings(api_key='unit-test-not-real'),store)) as client:
        rows=client.get('/api/uploads',headers={'X-Session-ID':old_owner})
        assert rows.status_code==200 and rows.headers['cache-control']=='no-store'
        assert [r['id'] for r in rows.json()['records']]==[record['id']]
        assert client.get('/api/uploads',headers={'X-Session-ID':new_session}).json()['records']==[]
        body={'session_id':new_session,'request_id':str(uuid4()),'scene_id':record['scene_id'],'zone_id':'A','dwell_seconds':3,'question':'有几辆车？'}
        assert client.post('/api/chat',json=body).status_code==404
        result=client.post('/api/chat',json=body,headers={'X-Media-Owner':old_owner})
        assert result.status_code==200 and result.json()['status']=='complete'
        assert store.remaining(new_session,5)==4
        client.get('/api/uploads',headers={'X-Session-ID':old_owner})
        assert store.remaining(new_session,5)==4
