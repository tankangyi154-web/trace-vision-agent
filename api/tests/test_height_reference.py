import math
import asyncio
import json
import pytest
from evals.height_geometry import Camera,head_from_foot,estimate_height
from api.visual_estimates import height_estimate


def test_projective_forward_inverse_preserves_known_heights_across_depth_positions():
    camera=Camera(720,-.5,300)
    for foot in (400,500,650):
        for height in (155,175,190):
            head=head_from_foot(foot,height,camera)
            assert estimate_height(head,foot,camera)==pytest.approx(height,abs=1e-8)


def test_level_camera_matches_the_analytic_pinhole_scale():
    # Camera at 300cm, floor 240px below centre, head 100px below centre:
    # height = 300 * (240 - 100) / 240 = 175cm.
    assert estimate_height(460,600,Camera(720,0,300))==pytest.approx(175)


@pytest.mark.parametrize('head,foot',[(math.nan,600),(100,100),(500,400),(-1,500),(100,721)])
def test_invalid_or_invisible_head_foot_pairs_are_rejected(head,foot):
    with pytest.raises(ValueError):estimate_height(head,foot,Camera(720,-.5,300))


def test_paper_reference_can_share_depth_without_pretending_to_stand_on_the_ground():
    row={'aspect':'height','status':'uncertain','evidence_ids':['v'],'height_estimate':{'range_cm':[160,180],
        'full_body_visible':True,'reference':{'name':'手中白色打印纸','height_cm':[21,22],'same_depth_plane':True}}}
    frames=[{'evidence_id':'v','pixels':[200,600],'bbox':[.2,.1,.6,.9],'flags':[]}]
    text,value=height_estimate(row,frames)
    assert '160—180厘米' in text and value['not_a_measurement']
    row['height_estimate']['reference']['same_depth_plane']=False
    with pytest.raises(ValueError):height_estimate(row,frames)
    row['height_estimate']['reference']['same_depth_plane']=True
    frames[0]['flags']=['touching_frame_edge']
    with pytest.raises(ValueError):height_estimate(row,frames)


def test_paper_context_keeps_the_real_image_answer_to_the_height_question_only():
    from api.agent import run_agent
    from api.config import Settings
    from api.tests.test_media_comparison import scene,inspect
    data=scene();calls=[]
    question='人 #48目测多高？按手中的纸张参照给粗略范围；以作者采用的美式Letter纸尺寸假设（短边21.59厘米、长边27.94厘米）比较，注意纸张横竖方向。依据不足就具体说明。'
    async def provider(messages,*_):
        calls.append(messages)
        row={'target_id':'48','aspect':'height','status':'uncertain','description':'头脚可见，手中白纸可作比例参照。',
            'reason':'纸张尺寸是假设，纸张角度和拍摄距离仍有影响。','evidence_ids':['v-48-0'],
            'height_estimate':{'range_cm':[160,180],'full_body_visible':True,'reference':{'name':'手中白色打印纸','height_cm':[21,22],'same_depth_plane':True}}}
        return {'choices':[{'message':{'content':json.dumps({'answer':'','fact_keys':[],'evidence_ids':[],
            'insufficient_evidence':True,'visual_observations':[row]})}}],'usage':{'prompt_tokens':10,'completion_tokens':10}}
    result=asyncio.run(run_agent(data,'A',3,question,[],Settings(),lambda _:None,provider=provider,
        media_context={'selected_target_id':'48'},media_inspection=lambda _:inspect(data)))
    assert len(calls)==1 and result['usage']['model_calls']==1
    assert [c['aspect'] for c in result['answer_coverage']]==['height']
    assert '160—180厘米' in result['answer']


@pytest.mark.parametrize('calls,request_calls',[(3,0),(0,1)])
def test_paid_height_check_budget_rejects_before_opening_a_network_client(monkeypatch,calls,request_calls):
    from evals import run_height_images as check
    from api.agent import AgentError
    monkeypatch.setattr(check,'calls',calls);monkeypatch.setattr(check,'request_calls',request_calls)
    def no_client(*_,**__):raise AssertionError('Budget exhaustion must precede network access')
    monkeypatch.setattr(check.httpx,'AsyncClient',no_client)
    with pytest.raises(AgentError) as error:asyncio.run(check.provider([],[],False))
    assert error.value.code=='height_check_budget' and check.calls==calls
