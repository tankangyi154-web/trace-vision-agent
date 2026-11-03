import pytest
from api.media_answer import present_answer
from api.media_plan import build_plan
from api.media_tools import MediaTools
from api.tests.test_media_comparison import scene,inspect


def test_uncertain_absence_keeps_its_material_reason_in_the_short_answer():
    row={'target_id':'48','aspect':'carrying','status':'uncertain','description':'未见明显手持物品。',
        'reason':'手部细节较小，不能完全排除小物件。'}
    original={'answer':'原始完整说明。','factual_basis':[{'key':'target48.carrying','text':'随身物品：未见明显手持物品。','source':'visual_model'}],
        'visual_observations':[row],'answer_coverage':[{'target':'48','aspect':'carrying','status':'uncertain'}],'citations':[]}
    result=present_answer(original,scene(),build_plan('人48手里拿什么？',scene()))
    assert '不能完全排除小物件' in result['answer']
    assert result['answer_details']==original['answer'] and result['answer_parts'][0]['status']=='interpretation'


def test_repeated_positive_description_is_shortened_without_dropping_an_aspect_or_caveat():
    descriptions={'gender':'短发、肩背较宽，整体外观偏男性化','body':'看起来身形中等偏结实，肩背较宽'}
    result={'answer':'完整原文保持不变','factual_basis':[{'key':f'target48.{a}','text':t,'source':'visual_model'} for a,t in descriptions.items()],
        'visual_observations':[{'target_id':'48','aspect':a,'status':'uncertain','description':t,'reason':'仅是外观解读。'} for a,t in descriptions.items()],
        'answer_coverage':[{'target':'48','aspect':a,'status':'uncertain'} for a in descriptions],'citations':[]}
    short=present_answer(result,scene(),build_plan('人48性别、身形怎么样？',scene()))
    assert short['answer'].count('肩背较宽')==1
    assert '外观偏男性化' in short['answer'] and '中等偏结实' in short['answer']
    assert len(short['answer_parts'])==2 and short['answer_details']==result['answer']


def tools_and_rows(status):
    data=scene();plan=build_plan('人48目测多高？',data)
    tools=MediaTools(data,plan=plan,inspection=lambda _:inspect(data));tools.execute('locate_object',{'target':'48'})
    height={'target_id':'48','aspect':'height','status':status,'description':'附近缺少可靠尺寸参照。','reason':'同距离的参照物尺寸无法确认。','evidence_ids':['v-48-0']}
    if status=='uncertain':height.update(height_estimate={'range_cm':[160,180],'full_body_visible':True,
        'reference':{'name':'手中白色打印纸','height_cm':[21,22],'same_depth_plane':True}})
    extra={'target_id':'48','aspect':'appearance','status':'clear','description':'戴着眼镜。','reason':'','evidence_ids':['v-48-0']}
    return tools,{'answer':'','fact_keys':[],'evidence_ids':[],'insufficient_evidence':True,'visual_observations':[height,extra]}


def test_a_height_estimate_cannot_grow_unrequested_glasses_or_clothing_claims():
    tools,obj=tools_and_rows('uncertain')
    with pytest.raises(ValueError,match='未被询问'):tools.validate_answer(obj)
    obj['visual_observations']=obj['visual_observations'][:1]
    assert tools.validate_answer(obj)['answer_coverage'][0]['aspect']=='height'


def test_a_genuine_insufficient_answer_can_still_offer_a_visible_fallback():
    tools,obj=tools_and_rows('insufficient')
    obj['visual_observations'][1]['description']='能看清深色上衣。'
    result=tools.validate_answer(obj)
    assert '深色上衣' in result['answer'] and result['answer_coverage'][0]['status']=='insufficient'
