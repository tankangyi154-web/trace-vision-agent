import asyncio,json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx,pytest
from api.config import Settings
from api.agent import AgentError
from api.remote_agent import RemoteAgent,installation_token

def test_shared_agent_works_without_a_distributed_provider_key():
    settings=Settings(remote_agent_url='https://example.test')
    assert not settings.api_key and settings.reason is None and settings.supports_images
    assert Settings(production=True,remote_agent_url='https://example.test').reason is not None

def test_installation_identity_is_stable_across_restarts_and_threads(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:values=list(pool.map(lambda _:installation_token(tmp_path),range(16)))
    assert len(set(values))==1 and len(values[0])==43
    assert installation_token(tmp_path)==values[0]

def test_gateway_request_only_sends_a_local_identity_and_reuses_its_question_ticket(tmp_path):
    calls=[]
    def handle(request):
        calls.append(request)
        assert request.headers['Authorization'].startswith('Bearer ')
        assert 'fixture-provider-secret' not in str(request.headers)
        if request.url.path=='/v1/questions':return httpx.Response(200,json={'ticket':'a'*64,'remaining':9})
        assert request.url.path=='/v1/questions/'+'a'*64+'/completions'
        return httpx.Response(200,json={'choices':[{'message':{'content':'回答'}}]})
    async def run():
        remote=RemoteAgent(Settings(remote_agent_url='https://example.test'),str(uuid4()),root=tmp_path,transport=httpx.MockTransport(handle))
        await remote.reserve()
        for _ in range(3):await remote.complete({'model':'deepseek-flash','messages':[]})
        assert remote.remaining==9
    asyncio.run(run());assert len(calls)==4

@pytest.mark.parametrize('code',['user_limit','daily_limit','monthly_limit'])
def test_gateway_quota_failures_remain_specific_without_returning_provider_errors(tmp_path,code):
    async def run():
        remote=RemoteAgent(Settings(remote_agent_url='https://example.test'),str(uuid4()),root=tmp_path,
            transport=httpx.MockTransport(lambda _:httpx.Response(429,json={'error':{'code':code,'message':'untrusted provider detail'}})))
        with pytest.raises(AgentError) as caught:await remote.reserve()
        assert caught.value.code==code and 'untrusted' not in caught.value.message
    asyncio.run(run())
