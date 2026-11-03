"""Regression: one numbered question can request several independent answers."""
import asyncio
import json

import pytest

from api.agent import AgentError,run_agent
from api.config import Settings
from api.media_profile import question_plan,target_number,track_profile
from api.media_tools import MediaCoverageError,MediaTools
from api.tests.test_media_tools import media

QUESTION='人30号是什么时间出现的，他的行动轨迹是什么样的，多久消失在画面里？性别是男性还是女性 身材是怎么样的 目测有多高？'
FACETS=['presence','trajectory','visibility','gender','body','height']


def recorded_scene():
    scene=media();scene['duration']=40
    times=[19,19.2,20,20.2,38.2,38.4]
    positions=[.1,.12,.48,.5,.8,.82]
    target={'id':'30','name':'人 #30','label':'person','first_seen':19,'last_seen':38.4,
            'evidence_ids':['own-1','own-2'],
            'samples':[{'t':t,'bbox':[x-.03,.4,x+.03,.6]} for t,x in zip(times,positions)]}
    scene['targets']=[target];scene['evidence'][0].update(t=19,track_id='30')
    scene['evidence'][1].update(t=38.4,track_id='30')
    return scene


def first_only(**updates):
    return {'answer':'他是男性，身高约一米八，刚走出画面。',
            'fact_keys':['target30.first_seen'],'evidence_ids':['own-1'],'rule_ids':[],
            'insufficient_evidence':False,**updates}


def test_original_multi_question_plan_includes_all_six_aspects_not_times_as_ids():
    assert question_plan(QUESTION)=={'targets':['30'],'facets':FACETS}
    assert question_plan('人30秒出现吗？19秒还是38.4秒？')['targets']==[]
    assert question_plan('人1.2秒出现，汽车在30秒离开')['targets']==[]
    assert question_plan('最后一帧有几辆车？')['facets']==[]
    assert question_plan('人 #030的轨迹，不用猜身高和性别')['facets']==['trajectory']
    assert target_number('人30号')=='30'
    assert target_number('19.2秒') is None


def test_route_and_missing_samples_are_computed_without_filling_gaps():
    scene=recorded_scene();profile=track_profile(scene,scene['targets'][0])
    assert [p['position'] for p in profile['trajectory']['points']]==['左侧中部','画面中央','右侧中部']
    visibility=profile['visibility']['value']
    assert visibility=={'last_seen':38.4,'tail_seconds':1.6,'gap_count':2,'missing_sample_seconds':18.4}
    assert '实际离开时刻无法确定' in profile['visibility']['text']
    assert '未识别时段的路线无法确认' in profile['trajectory']['text']
    assert '不能确定是离开、遮挡还是漏检' in profile['visibility']['text']


def test_missing_or_irregular_positions_never_turn_into_continuous_visibility():
    scene=recorded_scene();target=scene['targets'][0];target['samples']=[]
    profile=track_profile(scene,target)
    assert all(p['status']=='insufficient' for p in profile.values())
    target['samples']=[{'t':19.01,'bbox':[.1,.1,.2,.2]}]
    profile=track_profile(scene,target)
    assert profile['visibility']['value']['gap_count'] is None
    assert profile['visibility']['status']=='insufficient'
    scene['kind']='image'
    assert all(p['status']=='insufficient' for p in track_profile(scene,target).values())


def test_final_answer_completes_all_requested_aspects_even_if_model_selects_first_only():
    tools=MediaTools(recorded_scene(),question=QUESTION)
    with pytest.raises(MediaCoverageError):tools.validate_answer(first_only(fact_keys=[],evidence_ids=[]))
    result=tools.execute('locate_object',{'target':'人 #30'})
    assert len(json.dumps(result,ensure_ascii=False))<16000
    final=tools.validate_answer(first_only())
    assert [c['aspect'] for c in final['answer_coverage']]==FACETS
    assert [c['status'] for c in final['answer_coverage']]==['answered']*3+['insufficient']*3
    assert len(final['answer'].split('\n\n'))==6
    assert '19秒' in final['answer'] and '38.4秒' in final['answer']
    assert all(text in final['answer'] for text in ('路线','性别：','体型：','身高：'))
    assert '一米八' not in final['answer'] and '他是男性' not in final['answer']
    assert final['insufficient_evidence'] is True
    assert [c['t'] for c in final['citations']]==[19,38.4]


def test_cited_frame_focuses_the_queried_person_instead_of_the_frames_leading_car():
    scene=recorded_scene()
    scene['evidence'][0].update(track_id='3',target_ids=['3','30'])
    tools=MediaTools(scene,question=QUESTION);tools.execute('locate_object',{'target':'30'})
    final=tools.validate_answer(first_only())
    assert final['citations'][0]['track_id']=='30'
    assert final['citations'][0]['target_ids']==['30']


def test_single_photo_never_claims_a_first_appearance_time_or_route():
    scene=recorded_scene();scene['kind']='image'
    tools=MediaTools(scene,question='人30号什么时候出现？轨迹和消失时间呢？')
    tools.execute('locate_object',{'target':'30'});final=tools.validate_answer(first_only())
    assert '无法判断何时出现' in final['answer']
    assert all(c['status']=='insufficient' for c in final['answer_coverage'])
    assert '19秒' not in final['answer'] and final['insufficient_evidence']


def test_foreign_citations_and_facts_still_fail_even_when_prose_is_replaced():
    tools=MediaTools(recorded_scene(),question=QUESTION);tools.execute('locate_object',{'target':'30'})
    with pytest.raises(ValueError):tools.validate_answer(first_only(evidence_ids=['other-upload']))
    with pytest.raises(ValueError):tools.validate_answer(first_only(fact_keys=['target99.first_seen']))
    tools=MediaTools(recorded_scene(),question='性别和身高呢？')
    with pytest.raises(ValueError):tools.validate_answer(first_only(fact_keys=[],evidence_ids=['other-upload']))


def test_unknown_number_and_no_number_are_explicitly_unavailable():
    tools=MediaTools(recorded_scene(),question='人99号什么时候出现，往哪走？身高多少？')
    tools.execute('locate_object',{'target':'99'})
    final=tools.validate_answer(first_only(fact_keys=[],evidence_ids=[]))
    assert '没有编号 #99' in final['answer'] and final['insufficient_evidence']
    tools=MediaTools(recorded_scene(),question='他什么时候出现，轨迹如何？')
    final=tools.validate_answer(first_only(fact_keys=[],evidence_ids=[]))
    assert '告诉我画面里的编号' in final['answer']


def test_graph_reads_real_profile_before_model_and_accounts_for_actual_usage():
    calls=[]
    async def provider(messages,schemas,force):
        calls.append(messages)
        assert messages[-1]['role']=='tool'
        tool=json.loads(messages[-1]['content'])
        assert tool['first_seen']==19 and tool['track_summary']['trajectory']['points']
        assert 'secret' not in json.dumps(messages)
        return {'choices':[{'message':{'content':json.dumps(first_only())}}],
                'usage':{'prompt_tokens':80,'completion_tokens':40}}
    final=asyncio.run(run_agent(recorded_scene(),'A',3,QUESTION,[],Settings(),lambda _:None,provider=provider))
    assert len(calls)==1 and len(final['answer_coverage'])==6
    assert final['usage']['model_calls']==1 and final['usage']['tool_calls']==1
    assert final['tool_calls'][0]['name']=='locate_object'
    assert final['tool_calls'][0]['origin']=='question_plan'
    assert final['usage']['input_tokens']==80 and final['usage']['output_tokens']==40


def test_planned_profile_does_not_accept_a_foreign_citation_after_format_repairs():
    async def provider(messages,schemas,force):
        return {'choices':[{'message':{'content':json.dumps(first_only(evidence_ids=['other-upload']))}}],
                'usage':{'prompt_tokens':80,'completion_tokens':40}}
    with pytest.raises(AgentError) as error:
        asyncio.run(run_agent(recorded_scene(),'A',3,QUESTION,[],Settings(),lambda _:None,provider=provider))
    assert error.value.code=='invalid_citations'
    assert error.value.partial['usage']['model_calls']==3
    assert error.value.partial['usage']['tool_calls']==1
