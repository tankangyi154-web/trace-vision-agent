import asyncio
from copy import deepcopy
import json
import pytest
from api.agent import run_agent,context_size,AgentError
from api.config import Settings
from api.media_tools import MediaTools,MediaCoverageError
from api.tests.test_media_profile import recorded_scene,QUESTION,first_only


def frames_for(scene,ident='30'):
    updated=deepcopy(scene);frames=[]
    for index,t in enumerate((19,20.2,38.4)):
        evidence_id=f'visual-{ident}-{index}'
        frames.append({'evidence_id':evidence_id,'t':t,'pixels':[180,450],'flags':[]})
        updated['evidence'].append({'id':evidence_id,'t':t,'track_id':ident,'image_url':'/private/card.jpg?token=secret'})
    return {'scene':updated,'frames':frames,'images':['data:image/jpeg;base64,/9j/unit-test']*3}


def observations():
    return [
        {'target_id':'30','aspect':'body','status':'clear','description':'身体轮廓较清楚，外观看起来偏瘦。','reason':'','evidence_ids':['visual-30-0','visual-30-2']},
        {'target_id':'30','aspect':'gender','status':'insufficient','description':'可见短发，无法确认实际性别。','reason':'面部细节不足，外观也不能证明实际性别。','evidence_ids':['visual-30-0']},
        {'target_id':'30','aspect':'height','status':'insufficient','description':'能看见站姿，但不能可靠估计身高。','reason':'没有已知尺寸的参照或相机尺度标定。','evidence_ids':['visual-30-2']},
        {'target_id':'30','aspect':'appearance','status':'clear','description':'可见红色上衣和深色裤子。','reason':'','evidence_ids':['visual-30-0']},
    ]


def prepared_tools():
    scene=recorded_scene();tools=MediaTools(scene,question=QUESTION,inspection=lambda _:frames_for(scene))
    tool=tools.execute('locate_object',{'target':'30'})
    return tools,tool


def test_actual_frame_messages_are_private_but_output_contains_retrievable_evidence():
    tools,result=prepared_tools()
    assert 'base64' not in json.dumps(result) and 'secret' not in json.dumps(result)
    assert result['visual_evidence']['target_id']=='30'
    assert len(result['visual_evidence']['frames'])==3
    messages=tools.take_visual_messages()
    assert messages[0]['role']=='user' and len(messages[0]['content'])==4
    assert all(p['image_url']['url'].startswith('data:image/jpeg') for p in messages[0]['content'][1:])
    assert tools.take_visual_messages()==[]


def test_clear_body_is_described_from_images_instead_of_the_fixed_refusal():
    tools,_=prepared_tools()
    result=tools.validate_answer(first_only(visual_observations=observations()))
    assert result['visual_frame_count']==3
    assert '外观看起来偏瘦' in result['answer'] and '红色上衣' in result['answer']
    assert '当前系统没有可靠的体型分析结果' not in result['answer']
    assert next(c for c in result['answer_coverage'] if c['aspect']=='body')['status']=='answered'
    assert all(c['track_id']=='30' for c in result['citations'])
    assert all(f['source']=='visual_model' for f in result['factual_basis'] if f['key'].endswith(('.body','.gender','.height','.appearance')))


def test_missing_aspect_foreign_frame_and_unmeasured_height_are_rejected():
    tools,_=prepared_tools()
    with pytest.raises(MediaCoverageError):tools.validate_answer(first_only(visual_observations=observations()[:-2]))
    rows=observations();rows[0]['evidence_ids']=['own-1']
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))
    rows=observations();rows[2]['description']='身高大约175厘米。'
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))
    rows=observations();rows[2]['description']='大约175。'
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))
    rows=observations();rows[1]['description']='可以确认是男性。'
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))


def test_failed_image_read_is_not_presented_as_having_seen_a_blurry_person():
    def fail(_):raise ValueError('素材副本暂时无法读取。')
    tools=MediaTools(recorded_scene(),question=QUESTION,inspection=fail)
    tools.execute('locate_object',{'target':'30'})
    result=tools.validate_answer(first_only())
    assert result['visual_frame_count']==0 and '副本暂时无法读取' in result['answer']
    assert '模糊' not in result['answer']


def test_tiny_person_cannot_acquire_invented_hair_or_confident_body_type():
    tools,_=prepared_tools()
    for frame in tools.visual_frames['30']:frame['pixels']=[15,39]
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=observations()))
    rows=observations();rows[0].update(status='insufficient',description='无法确认胖瘦。',reason='目标太小，放大没有增加真实细节。')
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))
    rows[1]['description']='目标太小，无法辨认发型与面部细节，也无法确认实际性别。'
    result=tools.validate_answer(first_only(visual_observations=rows))
    assert '红色上衣' in result['answer']


def test_real_graph_attaches_pixels_to_one_metered_model_call_without_exposing_urls():
    scene=recorded_scene();calls=[]
    async def provider(messages,schemas,force):
        calls.append(messages)
        image_parts=[part for message in messages if isinstance(message.get('content'),list) for part in message['content'] if part['type']=='image_url']
        assert len(image_parts)==3
        assert all(message['role']=='user' for message in messages if isinstance(message.get('content'),list))
        assert 'secret' not in json.dumps(messages)
        return {'choices':[{'message':{'content':json.dumps(first_only(visual_observations=observations()))}}],
                'usage':{'prompt_tokens':321,'completion_tokens':123}}
    result=asyncio.run(run_agent(scene,'A',3,QUESTION,[],Settings(),lambda _:None,provider=provider,media_inspection=lambda _:frames_for(scene)))
    assert len(calls)==1 and result['usage']['model_calls']==1 and result['usage']['tool_calls']==1
    assert result['visual_frame_count']==3 and result['usage']['input_tokens']==321
    assert 'base64' not in json.dumps(result) and '外观看起来偏瘦' in result['answer']


def test_inline_images_have_their_own_budget_and_do_not_bypass_text_budget():
    image={'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+'x'*500000}}
    assert context_size([{'role':'user','content':[image]}])<1000
    assert context_size([{'role':'user','content':[image,{'type':'text','text':'x'*41000}]}])>40000
    with pytest.raises(AgentError):context_size([{'role':'user','content':[image]*7}])
    with pytest.raises(AgentError):context_size([{'role':'user','content':[{'type':'image_url','image_url':{'url':'http://external/private'}}]}])


def test_gender_presentation_can_be_described_without_assigning_gender_identity():
    tools,_=prepared_tools();rows=observations()
    rows[1].update(status='uncertain',description='外观偏男性化，短发、肩背轮廓较宽。',reason='仅指画面外观，实际性别身份无法确认。')
    result=tools.validate_answer(first_only(visual_observations=rows))
    assert '外观呈现：外观偏男性化' in result['answer']
    rows[1]['description']='看起来是男性。'
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))


def test_height_can_be_a_broad_visual_range_with_complete_body_and_explicit_reference():
    tools,_=prepared_tools();rows=observations()
    for frame in tools.visual_frames['30']:frame['bbox']=[.3,.1,.5,.9]
    rows[2].update(status='uncertain',description='站姿完整，附近可见同一地面的摩托车座。',reason='参照物使用常见尺寸假设，远近和视角带来误差。',
        height_estimate={'range_cm':[165,185],'full_body_visible':True,'reference':{'name':'左侧相近地面的摩托车座面','height_cm':[70,85],'same_ground_plane':True}})
    result=tools.validate_answer(first_only(visual_observations=rows))
    assert '165—185厘米' in result['answer'] and '目测参考' in result['answer']
    fact=next(f for f in result['factual_basis'] if f['key']=='target30.height')
    assert fact['source']=='visual_model' and fact['value']['not_a_measurement'] is True
    for frame in tools.visual_frames['30']:frame['flags']=['touching_frame_edge']
    with pytest.raises(ValueError):tools.validate_answer(first_only(visual_observations=rows))


def test_height_without_actual_reference_or_with_false_precision_is_still_rejected():
    from api.visual_estimates import height_estimate
    row={'aspect':'height','status':'uncertain','evidence_ids':['v'],'height_estimate':{'range_cm':[175,176],'full_body_visible':True,'reference':{'name':'摩托车座面','height_cm':[70,85],'same_ground_plane':True}}}
    frames=[{'evidence_id':'v','pixels':[200,500],'bbox':[.2,.1,.4,.9],'flags':[]}]
    with pytest.raises(ValueError):height_estimate(row,frames)
    row['height_estimate']['range_cm']=[165,185]
    row['height_estimate']['reference']['name']='其他成年人的平均身高'
    with pytest.raises(ValueError):height_estimate(row,frames)
