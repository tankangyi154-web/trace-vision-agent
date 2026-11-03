import json
from uuid import uuid4
from fastapi.testclient import TestClient
from api.config import Settings
from api.store import SQLiteStore
from api.index import create_app


def test_followup_uses_server_owned_verified_review_context(tmp_path,monkeypatch):
    rid=str(uuid4()); sid_review=str(uuid4()); store=SQLiteStore(tmp_path/'s.db'); sid=store.create_session()
    scope='harbor:A:5:harbor-T001-gap:baseline'
    store.reserve(sid,rid,'fp',{},'2026-10-31',5,50)
    store.finish(sid,rid,{'status':'complete','answer':'insufficient evidence','review_id':sid_review,
                         'investigation_id':'harbor-T001-gap'},scope,'initial')
    memory=json.loads(store.history(sid,scope)[-1]['content'])
    assert memory['schema']=='investigation-memory-v1' and memory['review_id']==sid_review
    class Service:
        def __init__(self,*args): pass
        def get(self,value):
            assert value==sid_review
            return {'status':'complete'}
    monkeypatch.setattr('api.index.ReviewService',Service)
    called={}
    async def agent(*args,**kwargs):
        called.update(kwargs)
        return {'answer':'followup','citations':[],'tool_calls':[]}
    monkeypatch.setattr('api.index.run_agent',agent)
    client=TestClient(create_app(Settings(api_key='unit-not-real'),store))
    response=client.post('/api/chat',json={'request_id':str(uuid4()),'session_id':sid,'scene_id':'harbor','zone_id':'A',
        'dwell_seconds':5,'investigation_id':'harbor-T001-gap','question':'what if threshold3?'})
    assert response.status_code==200
    assert called['review_id']==sid_review
