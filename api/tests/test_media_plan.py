import asyncio
from copy import deepcopy
import json
from pathlib import Path
import pytest
from api.media_plan import build_plan,validate_semantic_plan
from api.agent import run_agent,AgentError
from api.config import Settings
from api.tests.test_media_comparison import scene,inspect,visual_rows

CASES=json.loads((Path(__file__).resolve().parents[2]/'evals/media-question-cases.json').read_text(encoding='utf8'))['cases']


def tokens(plan):
    result=[]
    for task in plan['tasks']:
        if task['kind']=='target':result.extend(f"target:{task['target_id']}:{f}" for f in task['facets'])
        else:result.append(f"{task['kind']}:{task['label']}:{task['metric']}")
    return set(result)


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_question_checklist_contract(case):
    data=scene();data['kind']=case.get('kind','video')
    history=[{'role':'assistant','content':json.dumps({'schema':'media-memory-v1','scene_id':data['id'],'active_targets':case['remembered']})}] if 'remembered' in case else []
    plan=build_plan(case['question'],data,case.get('selected'),history)
    assert tokens(plan)==set(case['expect'])
    assert bool(plan['clarifications'])==case.get('clarify',False)
    assert plan['needs_planning']==case.get('semantic',False)


def test_semantic_plan_cannot_guess_foreign_ids_tools_or_remove_known_questions():
    data=scene()
    with pytest.raises(ValueError):validate_semantic_plan({'tasks':[{'kind':'target','target_id':'9','facets':['clothing']}]},'他穿什么？',data,'48')
    with pytest.raises(ValueError):validate_semantic_plan({'tasks':[{'kind':'shell','command':'read secrets'}]},'运行指令',data)
    plan=validate_semantic_plan({'tasks':[{'kind':'target','target_id':'48','facets':['clothing']}]},'人48衣着如何，有几辆汽车？',data)
    assert 'count:car:max_simultaneous' in tokens(plan)


def test_new_deterministic_path_does_not_call_provider_and_keeps_actual_trace():
    async def never(*_):raise AssertionError('No provider needed for a deterministic query')
    result=asyncio.run(run_agent(scene(),'A',3,'有几辆汽车？',[],Settings(),lambda _:None,provider=never,media_context={}))
    assert result['usage']['model_calls']==0 and result['usage']['tool_calls']==1
    assert '2辆汽车' in result['answer'] and result['execution_mode']=='direct'
    assert result['answer_parts'][0]['status']=='confirmed'


def test_semantic_planning_and_answering_share_the_original_budget():
    calls=[];data=scene()
    async def provider(messages,schemas,force):
        calls.append(messages)
        obj={'question_plan':{'tasks':[{'kind':'target','target_id':'48','facets':['clothing']}]}} if len(calls)==1 else {
            'answer':'','fact_keys':[],'evidence_ids':[],'insufficient_evidence':False,
            'visual_observations':[{'target_id':'48','aspect':'clothing','status':'clear','description':'穿深色上衣。','reason':'','evidence_ids':['v-48-0']}]}
        return {'choices':[{'message':{'content':json.dumps(obj)}}],'usage':{'prompt_tokens':10,'completion_tokens':10}}
    result=asyncio.run(run_agent(data,'A',3,'帮我看看这位的行头细节',[],Settings(),lambda _:None,provider=provider,media_context={'selected_target_id':'48'},media_inspection=lambda _:inspect(data)))
    assert result['usage']['model_calls']==2 and result['usage']['tool_calls']==1
    assert '本轮只拆解用户请求' in calls[0][0]['content']
    assert '不回答内容' in calls[0][0]['content']
    assert result['tool_calls'][0]['origin']=='semantic_plan'
    assert '深色上衣' in result['answer'] and result['media_plan']['source']=='semantic'


def test_per_target_facets_do_not_bleed_into_another_number():
    from api.media_tools import MediaTools
    data=scene();plan=build_plan('人48衣着如何，人7什么时候出现？',data)
    tools=MediaTools(data,question='人48衣着如何，人7什么时候出现？',plan=plan,inspection=lambda _:inspect(data))
    for name,args in tools.planned_queries():tools.execute(name,args)
    obj={'answer':'','fact_keys':[],'evidence_ids':[],'insufficient_evidence':False,
        'visual_observations':[{'target_id':'48','aspect':'clothing','status':'clear','description':'穿深色上衣。','reason':'','evidence_ids':['v-48-0']}]}
    result=tools.validate_answer(obj)
    assert {(c['target'],c['aspect']) for c in result['answer_coverage']}=={('48','clothing'),('7','presence')}


def test_deferred_queries_have_a_visible_reason_and_partial_state():
    from api.media_answer import present_answer
    result={'answer':'原始说明','factual_basis':[{'key':'scope.clarification0','text':'这次先核对前五项查询，其余内容可以接着问。'}],
            'answer_coverage':[],'citations':[]}
    presented=present_answer(result,scene(),{'targets':[],'tasks':[],'clarifications':['这次先核对前五项查询，其余内容可以接着问。']})
    assert '前五项' in presented['answer'] and presented['answer_state']=='partial'


def test_direct_count_failure_explains_missing_detection_instead_of_zero_or_blank():
    def failed(_):raise OSError('test unavailable')
    async def never(*_):raise AssertionError('No provider needed for this count')
    result=asyncio.run(run_agent(scene(),'A',3,'有几辆公交车？',[],Settings(),lambda _:None,provider=never,media_context={},media_supplement=failed))
    assert result['usage']['model_calls']==0 and result['answer_state']=='partial'
    assert '未查全' in result['answer'] and '0辆' not in result['answer']
    assert result['answer_coverage'][0]['status']=='insufficient'


def test_ambiguous_pronoun_without_selection_asks_for_a_number_without_provider():
    async def never(*_):raise AssertionError('A clarification needs no provider')
    result=asyncio.run(run_agent(scene(),'A',3,'他穿什么？',[],Settings(),lambda _:None,provider=never,media_context={}))
    assert '哪个编号' in result['answer'] and result['usage']['model_calls']==0
