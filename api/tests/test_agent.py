import asyncio
import json
import threading
import time
import pytest
from api.agent import run_agent, AgentError
from api.config import Settings
from api.tools import Toolset, retrieve_rules
from api.tests.test_domain import scene


def tool_call(name,args,ident='c1'):
    return {'id':ident,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}


def response(content=None,calls=None):
    return {'choices':[{'message':{'role':'assistant','content':content,'tool_calls':calls or []}}],
            'usage':{'prompt_tokens':20,'completion_tokens':10}}


def test_actual_graph_calls_tool_and_validates_citations():
    count=0; stages=[]
    async def provider(messages,tools,force_final):
        nonlocal count
        count+=1
        if count==1: return response(calls=[tool_call('calculate_dwell',{})])
        return response(json.dumps({'answer':'目标1可观测驻留0.5秒，证据 E1。','evidence_ids':['E1'],'rule_ids':[]}))
    result=asyncio.run(run_agent(scene([(0,.5),(.25,.5),(.5,.5)]),'A',.5,'哪个驻留最久',[],Settings(),stages.append,provider))
    assert result['citations'][0]['track_id']=='1'
    assert result['usage']=={'input_tokens':40,'output_tokens':20,'model_calls':2,'tool_calls':1,'usage_complete':True}
    assert result['tool_calls'][0]['name']=='calculate_dwell'
    assert any('工具' in s.get('stage','') for s in stages)


def test_hallucinated_or_unretrieved_evidence_rejected():
    t=Toolset(scene([(0,.5)]),'A',1)
    with pytest.raises(ValueError,match='did not retrieve'):
        t.validate_answer({'answer':'fake','evidence_ids':['E1']})
    t.execute('calculate_dwell',{})
    with pytest.raises(ValueError,match='did not retrieve'):
        t.validate_answer({'answer':'fake','evidence_ids':['E-UNKNOWN']})
    with pytest.raises(ValueError,match='must cite'):
        t.validate_answer({'answer':'uncited','evidence_ids':[]})


def test_model_and_tool_budgets_are_bounded():
    count=0
    async def provider(messages,tools,force_final):
        nonlocal count
        count+=1
        return response(calls=[tool_call('calculate_dwell',{},str(count))])
    with pytest.raises(AgentError,match='budget'):
        asyncio.run(run_agent(scene([(0,.5)]),'A',1,'repeat',[],Settings(),lambda x:None,provider))
    assert count==3


def test_many_tool_calls_do_not_overrun_budget():
    async def provider(*args):
        return response(calls=[tool_call('calculate_dwell',{},str(i)) for i in range(6)])
    with pytest.raises(AgentError,match='budget'):
        asyncio.run(run_agent(scene([(0,.5)]),'A',1,'repeat',[],Settings(),lambda x:None,provider))


def test_unknown_questions_can_honestly_have_no_evidence():
    async def provider(*args):
        return response(json.dumps({'answer':'没有标定，无法判断真实航速。','evidence_ids':[],'rule_ids':[],'insufficient_evidence':True}))
    result=asyncio.run(run_agent(scene([(0,.5)]),'A',1,'航速多少',[],Settings(),lambda x:None,provider))
    assert result['citations']==[]


def test_bm25_returns_relevant_rule_and_tool_rejects_parameters():
    assert retrieve_rules('驻留时长')[0]['id']=='R-DWELL'
    t=Toolset(scene([]),'A',1)
    with pytest.raises(ValueError): t.execute('search_events',{'limit':100})
    with pytest.raises(ValueError): t.execute('get_track',{'track_id':'1','path':'/secrets'})


def test_cancelled_tool_chain_does_not_start_another_tool(monkeypatch):
    cancelled=threading.Event(); entered=threading.Event(); finished=threading.Event(); executed=[]
    original=Toolset.execute
    def slow(self,name,args):
        executed.append(name)
        entered.set()
        cancelled.wait(timeout=2)
        try:return original(self,name,args)
        finally:finished.set()
    monkeypatch.setattr(Toolset,'execute',slow)
    async def provider(*args):
        return response(calls=[tool_call('calculate_dwell',{},'a'),tool_call('get_track',{'track_id':'1'},'b')])
    async def run():
        task=asyncio.create_task(run_agent(scene([(0,.5)]),'A',1,'test',[],Settings(),lambda _:None,provider,cancelled))
        assert await asyncio.to_thread(entered.wait,2)
        try:
            await asyncio.wait_for(task,timeout=.01)
        except asyncio.TimeoutError: cancelled.set()
        assert await asyncio.to_thread(finished.wait,2)
    asyncio.run(run())
    assert executed==['calculate_dwell']


def test_provider_output_limit_is_distinct_from_invalid_evidence():
    async def provider(*args):
        r=response('{"answer":"cut')
        r['choices'][0]['finish_reason']='length'
        return r
    with pytest.raises(AgentError) as e:
        asyncio.run(run_agent(scene([]),'A',1,'test',[],Settings(),lambda _:None,provider))
    assert e.value.code=='model_output_limit'


def test_standard_answer_can_correct_a_citation_once_inside_the_original_budget():
    count=0
    async def provider(messages,tools,force_final):
        nonlocal count
        count+=1
        if count==1:return response(calls=[tool_call('calculate_dwell',{})])
        if count==2:return response(json.dumps({'answer':'出现0.5秒。','evidence_ids':['unretrieved'],'rule_ids':[]}))
        assert force_final and 'E1' in messages[-1]['content']
        assert 'rule_ids：[]' in messages[-1]['content']
        return response(json.dumps({'answer':'画面中能确认出现0.5秒。','evidence_ids':['E1'],'rule_ids':[]}))
    result=asyncio.run(run_agent(scene([(0,.5),(.25,.5),(.5,.5)]),'A',.5,'概括出现情况',[],Settings(),lambda _:None,provider))
    assert result['citations'][0]['evidence_id']=='E1'
    assert result['usage']['model_calls']==3 and result['usage']['tool_calls']==1


def test_standard_correction_does_not_admit_an_unretrieved_id_or_keep_retrying():
    count=0
    async def provider(*args):
        nonlocal count
        count+=1
        if count==1:return response(calls=[tool_call('calculate_dwell',{})])
        return response(json.dumps({'answer':'未通过的说明。','evidence_ids':['unretrieved'],'rule_ids':[]}))
    with pytest.raises(AgentError) as error:
        asyncio.run(run_agent(scene([(0,.5),(.25,.5),(.5,.5)]),'A',.5,'概括',[],Settings(),lambda _:None,provider))
    assert error.value.code=='invalid_citations' and count==3
