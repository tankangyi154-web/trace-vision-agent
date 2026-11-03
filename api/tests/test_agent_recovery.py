import asyncio,json
from uuid import uuid4
import httpx,pytest
from api.agent import run_agent,AgentError
from api.config import Settings
from api.remote_agent import RemoteAgent
from api.tests.test_media_comparison import scene,inspect
from api.media_plan import build_plan
from api.media_profile import appearance_duration

def test_original_duration_and_height_question_is_split_without_accidental_people_count():
    plan=build_plan('人48出现了多少秒 目测多高',scene())
    assert plan['facets']==['duration','height'] and plan['targets']==['48'] and not plan.get('counts')
    assert not plan['needs_planning']

@pytest.mark.parametrize('question,facets',[('人48出现了几秒？',{'duration'}),('人48在第几秒出现？',{'presence'}),('人48什么时候出现，累计出现多久？',{'presence','duration'})])
def test_duration_and_first_seen_have_distinct_meanings(question,facets):
    assert set(build_plan(question,scene())['facets'])==facets

def test_duration_query_works_even_when_provider_is_unreachable():
    async def unavailable(*args):raise AssertionError('Local duration must not call a provider')
    data=scene()
    result=asyncio.run(run_agent(data,'A',3,'人48出现了多少秒',[],Settings(),lambda _:None,provider=unavailable,media_context={}))
    expected=appearance_duration(data,next(t for t in data['targets'] if t['id']=='48'))
    assert f"{expected['observed_seconds']:g}秒" in result['answer']
    assert result['usage']['model_calls']==0 and '汽车' not in result['answer']

def test_mixed_question_keeps_duration_and_never_fabricates_or_blames_blurry_images_on_network_failure():
    async def unavailable(*args):raise AgentError('connection_failed','网络暂不可用')
    data=scene()
    result=asyncio.run(run_agent(data,'A',3,'人48出现了多少秒 目测多高',[],Settings(),lambda _:None,provider=unavailable,media_context={},media_inspection=lambda _:inspect(data)))
    assert result['answer_state']=='partial' and result['connection']['retryable']
    assert '累计识别到' in result['answer'] and '在线画面分析暂未完成' in result['answer']
    assert '参照数据' not in result['answer'] and '模糊' not in result['answer']
    assert result['visual_frame_count']==0 and {p['key'] for p in result['answer_parts']} >= {'target48.duration','target48.height'}

def test_continuous_duration_is_not_replaced_by_total():
    async def never(*args):raise AssertionError('No provider')
    result=asyncio.run(run_agent(scene(),'A',3,'人48连续出现了多少秒',[],Settings(),lambda _:None,provider=never,media_context={}))
    assert '最长连续' in result['answer'] and '累计' not in result['answer']

def test_reservation_reconnect_reuses_original_id_without_repeating_paid_completion(tmp_path):
    calls=[];rid=str(uuid4())
    def handler(request):
        calls.append(request)
        if request.url.path=='/v1/questions':
            assert json.loads(request.content)['request_id']==rid
            if len(calls)==1:raise httpx.ReadTimeout('private text must not be logged',request=request)
            return httpx.Response(200,json={'ticket':'a'*64,'remaining':9})
        return httpx.Response(200,json={'choices':[]})
    async def run():
        remote=RemoteAgent(Settings(remote_agent_url='https://example.test'),rid,root=tmp_path,transport=httpx.MockTransport(handler))
        await remote.complete({'messages':[]})
    asyncio.run(run())
    assert len(calls)==3 and sum(r.url.path.endswith('/completions') for r in calls)==1
    assert 'private text' not in (tmp_path/'work/agent-connection.log').read_text()

def test_only_connection_establishment_failure_can_retry_a_completion(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:raise httpx.ConnectError('test',request=request)
        return httpx.Response(200,json={'choices':[]})
    async def run():
        remote=RemoteAgent(Settings(remote_agent_url='https://example.test'),str(uuid4()),root=tmp_path,transport=httpx.MockTransport(handler));remote.ticket='a'*64
        await remote.complete({'messages':[]})
    asyncio.run(run());assert len(calls)==2

def test_unknown_completion_result_never_retries_automatically(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request);raise httpx.ReadTimeout('test',request=request)
    async def run():
        remote=RemoteAgent(Settings(remote_agent_url='https://example.test'),str(uuid4()),root=tmp_path,transport=httpx.MockTransport(handler));remote.ticket='a'*64
        with pytest.raises(AgentError) as e:await remote.complete({'messages':[]})
        assert e.value.code=='connection_timeout' and e.value.partial['connection']['retryable'] is False
    asyncio.run(run());assert len(calls)==1

def test_offline_recovery_is_bounded_and_logs_no_identity_or_content(tmp_path):
    calls=[]
    def handler(request):calls.append(request);raise httpx.ConnectError('secret diagnostic text',request=request)
    async def run():
        remote=RemoteAgent(Settings(remote_agent_url='https://example.test'),str(uuid4()),root=tmp_path,transport=httpx.MockTransport(handler))
        with pytest.raises(AgentError) as e:await remote.reserve()
        assert e.value.partial['connection']['attempts']==3
        text=(tmp_path/'work/agent-connection.log').read_text()
        assert remote.token not in text and 'secret diagnostic text' not in text
    asyncio.run(run());assert len(calls)==3

def _client_with_media(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from api.index import create_app
    from api.store import SQLiteStore
    from api.uploads import UploadService
    data=scene();data['id']='upload-'+str(uuid4())
    service=UploadService(tmp_path/'uploads');cached=[]
    monkeypatch.setattr('api.index.UploadService',lambda **kwargs:service)
    monkeypatch.setattr(service,'scene',lambda *args:data)
    monkeypatch.setattr(service,'cached_answer',lambda *args:None)
    monkeypatch.setattr(service,'cache_answer',lambda *args:cached.append(args))
    monkeypatch.setattr(service,'inspect_target',lambda *args:inspect(data))
    client=TestClient(create_app(Settings(remote_agent_url='https://example.test'),SQLiteStore(tmp_path/'state.db')))
    owner=client.post('/api/sessions').json()['session_id']
    body={'request_id':str(uuid4()),'session_id':owner,'scene_id':data['id'],'zone_id':'A','dwell_seconds':3,'selected_target_id':'48'}
    return client,body,cached

def test_http_local_questions_never_reserve_cloud_quota(tmp_path,monkeypatch):
    async def never(*args):raise AssertionError('Cloud reservation must be lazy')
    monkeypatch.setattr(RemoteAgent,'reserve',never)
    client,body,_=_client_with_media(tmp_path,monkeypatch)
    with client:
        response=client.post('/api/chat',json={**body,'question':'人48出现多少秒？'})
    assert response.status_code==200 and response.json()['status']=='complete'
    assert response.json()['usage']['model_calls']==0 and '累计识别到' in response.json()['answer']

def test_http_network_partial_is_not_cached_as_a_successful_visual_answer(tmp_path,monkeypatch):
    async def offline(*args):raise AgentError('connection_failed','暂未连接')
    monkeypatch.setattr(RemoteAgent,'reserve',offline)
    client,body,cached=_client_with_media(tmp_path,monkeypatch)
    with client:
        response=client.post('/api/chat',json={**body,'question':'人48出现多少秒，目测多高？'})
    data=response.json()
    assert response.status_code==200 and data['status']=='complete' and data['answer_state']=='partial'
    assert data['connection']['code']=='connection_failed' and '累计识别到' in data['answer']
    assert not cached
