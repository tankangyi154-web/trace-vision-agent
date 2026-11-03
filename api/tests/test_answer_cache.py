from copy import deepcopy
import json
import pytest
from api.uploads import UploadService,UploadError
from api.answer_cache import answer_cache_key
from api.config import Settings


def record(service,owner):
    public=service.reserve(owner,'test.mp4',100,[0])
    job=service._read(public['id'])
    job.update(status='complete',expires_at=None,result={'revision':1,'cache_sha256':'source-v1','source_sha256':'original',
        'media':'r1.webm','poster':'poster.jpg','evidence':[{'id':'own','t':0,'image':'poster.jpg','track_id':'48'}],
        'highlights':[],'targets':[{'id':'48','name':'人 #48','label':'person','evidence_ids':['own'],'samples':[]}],
        'labels':{'person':'人'},'kind':'video','duration':1,'sample_fps':5})
    service._write(job)
    return job


def test_cache_owner_revision_and_citation_checks_do_not_reset_quota_or_expose_a_cache_asset(tmp_path):
    service=UploadService(tmp_path/'jobs');job=record(service,'owner')
    result={'answer':'穿深色上衣。','citations':[{'evidence_id':'own','track_id':'48','t':0,'image_url':'/private/image'}],
        'visual_frame_count':1,'usage':{'model_calls':1,'tool_calls':1},'tool_calls':[{'name':'locate_object'}]}
    service.cache_answer(job['scene_id'],'owner','key',result)
    with pytest.raises(UploadError):service.cached_answer(job['scene_id'],'wrong','key')
    cached=service.cached_answer(job['scene_id'],'owner','key')
    assert cached['cache_hit'] and cached['usage']['model_calls']==0 and cached['tool_calls']==[]
    with pytest.raises(UploadError):service.asset(job['id'],'answer-cache.json',job['asset_token'])
    job['result']['revision']=2;service._write(job)
    assert service.cached_answer(job['scene_id'],'owner','key') is None
    service.delete(job['id'],'owner');assert not service._path(job['id']).exists();service.close()


def test_key_changes_for_selected_target_revision_prompt_or_model_but_not_irrelevant_history(tmp_path):
    service=UploadService(tmp_path/'jobs');job=record(service,'owner');scene=job['result'];scene['id']=job['scene_id']
    settings=Settings()
    first=answer_cache_key(scene,'人48穿什么？',None,[],settings)
    history=[{'role':'assistant','content':json.dumps({'schema':'media-memory-v1','scene_id':scene['id'],'active_targets':['48']})}]
    assert answer_cache_key(scene,'人48穿什么？',None,history,settings)==first
    assert answer_cache_key(scene,'人48穿什么？','48',history,settings)!=first
    changed=deepcopy(scene);changed['revision']=2
    assert answer_cache_key(changed,'人48穿什么？',None,[],settings)!=first
    assert answer_cache_key(scene,'人48穿什么？',None,[],Settings(model='different-model'))!=first
    service.close()


def test_http_selected_target_is_bound_to_authorized_media_before_quota_or_agent(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from uuid import uuid4
    from api.index import create_app
    from api.store import SQLiteStore
    store=SQLiteStore(tmp_path/'api.sqlite3');owner=store.create_session()
    service=UploadService(tmp_path/'jobs');job=record(service,owner);service.close()
    original=UploadService.__init__
    def init(self,*args,**kwargs):kwargs['directory']=tmp_path/'jobs';original(self,*args,**kwargs)
    monkeypatch.setattr(UploadService,'__init__',init)
    calls=[]
    async def agent(*args,**kwargs):
        calls.append(kwargs['media_context']);return {'answer':'已核对。','citations':[],'rule_citations':[],'tool_calls':[],'usage':{'model_calls':0,'tool_calls':1,'input_tokens':0,'output_tokens':0}}
    monkeypatch.setattr('api.index.run_agent',agent)
    with TestClient(create_app(Settings(api_key='not-real'),store)) as client:
        body={'request_id':str(uuid4()),'session_id':owner,'scene_id':job['scene_id'],'zone_id':'A','dwell_seconds':3,'question':'他什么时候出现？','selected_target_id':'9'}
        assert client.post('/api/chat',json=body).status_code==422
        assert store.remaining(owner,5)==5 and not calls
        body['selected_target_id']='48'
        response=client.post('/api/chat',json=body)
        assert response.status_code==200 and calls==[{'selected_target_id':'48'}]
        assert store.remaining(owner,5)==4
