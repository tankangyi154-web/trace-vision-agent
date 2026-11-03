import asyncio
from copy import deepcopy
import json
import pytest
from api.agent import run_agent
from api.config import Settings
from api.media_profile import question_plan,appearance_duration
from api.media_tools import MediaTools

QUESTION='画面里出现最长的人和汽车分别是编号几，人48号是什么性别 身高多高 什么身材'


def scene():
    targets=[];evidence=[]
    for ident,label,times in [('7','person',[0,.2,.4,1.6,1.8]),('48','person',[.4,.6,.8,1,1.2,1.4,1.6]),('2','car',[0,.2,.4]),('9','car',[.6,.8,1,1.2,1.4,1.6,1.8])]:
        en='人' if label=='person' else '汽车';ids=[f'e-{ident}']
        targets.append({'id':ident,'name':f'{en} #{ident}','label':label,'first_seen':times[0],'last_seen':times[-1],'evidence_ids':ids,
            'samples':[{'t':t,'bbox':[.3,.1,.5,.9]} for t in times]})
        evidence.append({'id':ids[0],'t':times[0],'track_id':ident,'target_ids':[ident],'image_url':'/private/card.jpg?token=secret'})
    return {'id':'upload-comparison','data_kind':'uploaded_media','source_sha256':'same-source','kind':'video','duration':2,'sample_fps':5,'labels':{'person':'人','car':'汽车'},'targets':targets,'evidence':evidence,'highlights':[],
        'classes':[0,2],'class_labels':['person','car'],'class_names':['人','汽车'],'counts':[{'label':'person','name':'人','count':2,'max_simultaneous':2},{'label':'car','name':'汽车','count':2,'max_simultaneous':2}]}


def inspect(data):
    updated=deepcopy(data);frames=[]
    for i,t in enumerate((.4,1,1.6)):
        ident=f'v-48-{i}'
        frames.append({'evidence_id':ident,'t':t,'pixels':[200,700],'bbox':[.3,.1,.5,.9],'flags':[]})
        updated['evidence'].append({'id':ident,'t':t,'track_id':'48','target_ids':['48'],'image_url':'/private/card.jpg?token=secret'})
    return {'scene':updated,'frames':frames,'images':['data:image/jpeg;base64,/9j/unit-test']*3}


def visual_rows():
    return [{'target_id':'48','aspect':'gender','status':'uncertain','description':'外观偏男性化，短发、肩背较宽。','reason':'仅描述外观呈现，不代表实际性别身份。','evidence_ids':['v-48-0']},
        {'target_id':'48','aspect':'body','status':'clear','description':'身形中等偏结实，肩背较宽。','reason':'','evidence_ids':['v-48-0']},
        {'target_id':'48','aspect':'height','status':'insufficient','description':'脚部被遮挡，无法给出可靠的身高范围。','reason':'脚部没有完整出现，旁边物体远近也不同。','evidence_ids':['v-48-0']}]


def answer():return {'answer':'','fact_keys':[],'evidence_ids':[],'rule_ids':[],'insufficient_evidence':True,'visual_observations':visual_rows()}


def test_original_question_plans_both_global_categories_before_numbered_appearance():
    plan=question_plan(QUESTION)
    assert plan['targets']==['48'] and plan['facets']==['gender','body','height']
    assert plan['rankings']==[{'label':'person','metric':'observed_seconds'},{'label':'car','metric':'observed_seconds'}]
    assert question_plan('人48出现最久吗')['targets']==['48']
    assert 'rankings' not in question_plan('人48出现最久吗')
    assert [r['label'] for r in question_plan('出现最久的公交车和自行车分别是哪个编号？')['rankings']]==['bus','bicycle']


def test_ranking_uses_actual_adjacent_samples_instead_of_first_last_span():
    data=scene();tools=MediaTools(data)
    duration=appearance_duration(data,data['targets'][0])
    assert duration=={'observed_seconds':.6,'longest_interval_seconds':.4}
    result=tools.execute('rank_objects',{'label':'person','metric':'observed_seconds'})
    assert result['ranking'][0]['id']=='48' and result['ranking'][0]['seconds']==1.2
    assert '48' in result['metrics'][0]['text'] and 'secret' not in json.dumps(result)
    assert tools.execute('rank_objects',{'label':'汽车','metric':'longest_interval_seconds'})['ranking'][0]['id']=='9'


def test_original_mixed_request_cannot_drop_global_answer_when_model_only_returns_visuals():
    data=scene();tools=MediaTools(data,question=QUESTION,inspection=lambda _:inspect(data))
    for name,args in tools.planned_queries():tools.execute(name,args)
    final=tools.validate_answer(answer())
    paragraphs=final['answer'].split('\n\n')
    assert '人 #48' in paragraphs[0] and '1.2秒' in paragraphs[0]
    assert '汽车 #9' in paragraphs[1] and '1.2秒' in paragraphs[1]
    assert '男性化' in final['answer'] and '偏结实' in final['answer']
    assert len(final['answer_coverage'])==5
    assert all(c['status']=='answered' for c in final['answer_coverage'][:2])
    assert next(c for c in final['citations'] if c['evidence_id']=='e-9')['track_id']=='9'
    assert 'e-48' in [c['evidence_id'] for c in final['citations']]


def test_mixed_query_runs_three_real_metered_tools_before_one_model_call():
    data=scene();calls=[]
    async def provider(messages,schemas,force):
        calls.append(messages)
        assert len([m for m in messages if m['role']=='tool'])==3
        assert 'secret' not in json.dumps(messages)
        return {'choices':[{'message':{'content':json.dumps(answer())}}],'usage':{'prompt_tokens':150,'completion_tokens':80}}
    final=asyncio.run(run_agent(data,'A',3,QUESTION,[],Settings(),lambda _:None,provider=provider,media_inspection=lambda _:inspect(data)))
    assert len(calls)==1 and final['usage']['tool_calls']==3
    assert [c['name'] for c in final['tool_calls']]==['rank_objects','rank_objects','locate_object']
    assert all(c['origin']=='question_plan' for c in final['tool_calls'])
    assert '汽车 #9' in final['answer'] and final['visual_frame_count']==3


def test_rank_only_no_id_and_ties_are_explicit_without_requiring_a_person_number():
    data=scene();data['targets'][0]['samples']=deepcopy(data['targets'][1]['samples'])
    tools=MediaTools(data,question='出现最久的人是哪个编号？')
    for name,args in tools.planned_queries():tools.execute(name,args)
    final=tools.validate_answer({'answer':'','fact_keys':[],'evidence_ids':[],'insufficient_evidence':True})
    assert '并列' in final['answer'] and '人 #7' in final['answer'] and '人 #48' in final['answer']
    assert '告诉我' not in final['answer']


def test_missing_samples_and_still_images_are_not_ranked_by_invented_durations():
    data=scene();data['targets'][0]['samples']=[]
    result=MediaTools(data).execute('rank_objects',{'label':'人','metric':'observed_seconds'})
    assert result['ranking']==[] and '缺少' in result['metrics'][0]['text']
    data['kind']='image'
    assert '单张图片' in MediaTools(data).execute('rank_objects',{'label':'人','metric':'observed_seconds'})['metrics'][0]['text']
