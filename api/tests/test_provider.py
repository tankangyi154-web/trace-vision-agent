import asyncio
import json
import httpx
from api.agent import run_agent
from api.config import Settings
from api.tests.test_domain import scene


def test_deepseek_official_payload_disables_thinking_without_qwen_parameters(monkeypatch):
    calls=[]
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,**kwargs):
            calls.append((url,kwargs))
            return httpx.Response(200,request=httpx.Request('POST',url),json={
                'choices':[{'message':{'role':'assistant','content':json.dumps({'answer':'无法判断真实航速。','evidence_ids':[],'rule_ids':[],'insufficient_evidence':True})}}],
                'usage':{'prompt_tokens':10,'completion_tokens':5}})
    monkeypatch.setattr('api.agent.httpx.AsyncClient',Client)
    asyncio.run(run_agent(scene([]),'A',3,'航速',[],Settings(api_key='unit-test-not-real'),lambda _:None))
    assert len(calls)==1
    url,kwargs=calls[0]
    assert url=='https://api.deepseek.com/chat/completions'
    assert kwargs['json']['model']=='deepseek-flash'
    assert kwargs['json']['thinking']=={'type':'disabled'}
    assert 'enable_thinking' not in kwargs['json']


def test_qwen_remains_selectable(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','qwen')
    monkeypatch.setenv('LLM_MODEL','qwen-plus')
    monkeypatch.setenv('DASHSCOPE_API_KEY','unit-test-not-real')
    settings=Settings.load()
    assert settings.provider=='qwen'
    assert settings.base_url=='https://dashscope.aliyuncs.com/compatible-mode/v1'
