import hashlib
import json
import threading
from types import SimpleNamespace
import pytest


def failed_job(tmp_path,monkeypatch):
    from api.uploads import UploadService
    from vision.source_cache import write_source_cache
    service=UploadService(tmp_path/'uploads')
    monkeypatch.setattr(service,'available',lambda:True)
    monkeypatch.setattr(service._pool,'submit',lambda *args:None)
    public=service.reserve('owner','test.jpg',100,[0])
    ident=public['id'];directory=service._path(ident)
    (directory/'analysis-source.png').write_bytes(b'normalized fixture')
    sha=hashlib.sha256(b'original fixture').hexdigest()
    write_source_cache(directory,{'kind':'image','cache_file':'analysis-source.png','source_sha256':sha,
        'duration':0,'sample_fps':0,'width':32,'height':32,'processed_frames':1,'source_width':32,'source_height':32})
    service._update(ident,status='failed',source_sha256=sha,processed=1,total=1,error='interrupted')
    return service,ident,directory


def test_retry_reuses_integrity_bound_private_cache_without_reupload(tmp_path,monkeypatch):
    from api.uploads import UploadError
    service,ident,directory=failed_job(tmp_path,monkeypatch)
    with pytest.raises(UploadError):service.retry(ident,'another-owner')
    assert service.get(ident,'owner')['can_retry']
    retry=service.retry(ident,'owner')
    assert retry['id']==ident and retry['status']=='queued' and retry['classes']==[0]
    assert retry['processed']==0 and retry['error'] is None
    assert not list(directory.glob('source.*'))
    assert service.retry(ident,'owner')['status']=='queued' # No duplicate work.
    service.close()


@pytest.mark.parametrize('tamper',['bytes','source','path'])
def test_retry_rejects_changed_cache_or_source_binding(tmp_path,monkeypatch,tamper):
    from api.uploads import UploadError
    service,ident,directory=failed_job(tmp_path,monkeypatch)
    path=directory/'source-cache.json';data=json.loads(path.read_text())
    if tamper=='bytes':(directory/'analysis-source.png').write_bytes(b'changed')
    elif tamper=='source':data['source_sha256']='0'*64
    else:data['cache_file']='../outside.png'
    path.write_text(json.dumps(data))
    with pytest.raises(UploadError,match='素材副本缺失'):service.retry(ident,'owner')
    assert service.get(ident,'owner')['status']=='failed'
    service.close()


def test_worker_deadline_is_reported_as_timeout_with_progress_retained(tmp_path,monkeypatch):
    import api.uploads as module
    service,ident,_=failed_job(tmp_path,monkeypatch)
    service._done[ident]=threading.Event()
    process=SimpleNamespace(stdout=[json.dumps({'stage':'detecting','processed':448,'total':585})],
        wait=lambda:1,poll=lambda:1)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:process)
    monkeypatch.setattr(module,'ProcessTree',lambda p:SimpleNamespace(kill=lambda:None,close=lambda:None))
    class Deadline:
        def __init__(self,seconds,callback):self.callback=callback
        def start(self):self.callback()
        def cancel(self):pass
    monkeypatch.setattr(module.threading,'Timer',Deadline)
    service._run(ident)
    job=service.get(ident,'owner')
    assert job['status']=='failed' and job['error_code']=='timeout'
    assert job['processed']==448 and job['total']==585 and job['can_retry']
    assert '处理上限' in job['error'] and '换一个文件' not in job['error']
    assert service._done[ident].is_set()
    service.close()
