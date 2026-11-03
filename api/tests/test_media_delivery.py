import json,os,threading,time
from types import SimpleNamespace
import pytest
from vision.media_scope import validate_scope,resolve_scope

def test_video_scope_is_explicit_bounded_and_cannot_silently_clip_invalid_input():
    assert validate_scope(None) is None
    assert resolve_scope(None,33.3)['partial'] is False
    scope=resolve_scope({'start_seconds':10,'end_seconds':20},33.3)
    assert scope['partial'] and scope['time_origin']=='selected_clip' and scope['source_duration_seconds']==33.3
    for value in [{'start_seconds':10,'end_seconds':5},{'start_seconds':False,'end_seconds':5},{'start_seconds':0,'end_seconds':float('nan')},{'start_seconds':0,'end_seconds':121},{'start_seconds':0,'end_seconds':5,'extra':True}]:
        with pytest.raises(ValueError,match='segment'):validate_scope(value)
    with pytest.raises(ValueError,match='segment'):resolve_scope({'start_seconds':0,'end_seconds':40},33.3)
    with pytest.raises(ValueError,match='segment'):validate_scope({'start_seconds':0,'end_seconds':5},'image')

@pytest.mark.parametrize('change',['none','owner','classes','scope','pipeline'])
def test_result_reuse_requires_same_owner_source_classes_scope_and_pipeline(tmp_path,monkeypatch,change):
    import api.uploads as module
    service=module.UploadService(tmp_path/'jobs');monkeypatch.setattr(service,'available',lambda:True)
    submissions=[];monkeypatch.setattr(service._pool,'submit',lambda *args:submissions.append(args))
    monkeypatch.setattr(module,'pipeline_fingerprint',lambda:'v1')
    def upload(owner,classes,scope=None):
        job=service.reserve(owner,'clip.mp4',4,classes,scope)
        (service._path(job['id'])/'source.mp4').write_bytes(b'same')
        return service.start(job['id'],owner)
    first=upload('owner',[0,2]);ident=first['id']
    result={'kind':'video','media':'video.webm','poster':'poster.jpg','evidence':[],'highlights':[]}
    service._update(ident,status='complete',result=result);service._done[ident].set()
    if change=='pipeline':monkeypatch.setattr(module,'pipeline_fingerprint',lambda:'v2')
    owner='someone-else' if change=='owner' else 'owner'
    second=upload(owner,[0,1] if change=='classes' else [2,0],{'start_seconds':1,'end_seconds':2} if change=='scope' else None)
    if change=='none':
        assert second['id']==ident and second['reused_result'] and len(submissions)==1
        assert len(list(service.directory.glob('*/job.json')))==1
    else:assert second['id']!=ident and second['status']=='queued' and len(submissions)==2
    service.close()

def test_active_owned_queue_is_not_deleted_by_temporary_retention(tmp_path):
    from api.uploads import UploadService
    service=UploadService(tmp_path/'jobs');job=service.reserve('owner','x.mp4',1,[0]);ident=job['id']
    service._done[ident]=threading.Event()
    service._update(ident,status='queued',expires_at=time.time()-1,manager_pid=os.getpid())
    service.cleanup();assert service.get(ident,'owner')['status']=='queued'
    service._done[ident].set();service._update(ident,status='failed',expires_at=time.time()-1)
    service.cleanup();assert not service._path(ident).exists()
    service.close()

@pytest.mark.parametrize('device,total,expected',[('cuda:0',585,300),('cpu',100,300),('cpu',585,900)])
def test_worker_budget_matches_actual_device_and_frame_volume(tmp_path,monkeypatch,device,total,expected):
    import api.uploads as module
    service=module.UploadService(tmp_path/'jobs');job=service.reserve('owner','x.mp4',1,[0]);ident=job['id']
    process=SimpleNamespace(stdout=[json.dumps({'stage':'loading','device':device,'total':total})],wait=lambda:1,poll=lambda:1)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:process)
    monkeypatch.setattr(module,'ProcessTree',lambda p:SimpleNamespace(kill=lambda:None,close=lambda:None))
    budgets=[]
    class Timer:
        def __init__(self,seconds,callback):budgets.append(seconds)
        def start(self):pass
        def cancel(self):pass
    monkeypatch.setattr(module.threading,'Timer',Timer)
    service._run(ident)
    assert expected-1<=budgets[-1]<=expected
    service.close()
