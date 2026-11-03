import pytest


def media():
    return {'id':'upload-one','data_kind':'uploaded_media','kind':'video','duration':2,
        'sample_fps':5,'labels':{'car':'汽车','person':'人'},
        'targets':[{'id':'1','label':'car','name':'目标1','first_seen':.2,'last_seen':1.8,'evidence_ids':['own-1','own-2']},
                   {'id':'2','label':'car','name':'目标2','first_seen':.6,'last_seen':1.2,'evidence_ids':['own-2']}],
        'counts':[{'label':'car','name':'汽车','count':2,'max_simultaneous':2}],
        'highlights':[{'id':'own-2','t':1.2,'description':'画面中标记2个目标','target_ids':['1','2']}],
        'evidence':[{'id':'own-1','t':.2,'track_id':'1','image_url':'/private/first.jpg?token=secret'},
                    {'id':'own-2','t':1.2,'track_id':'1','image_url':'/private/second.jpg?token=secret'}]}


def test_count_and_appearance_use_current_observations_and_keep_asset_token_out_of_tools():
    from api.media_tools import MediaTools
    tools=MediaTools(media())
    r=tools.execute('count_objects',{'label':'车辆'})
    assert r['count']==2 and r['max_simultaneous']==2
    assert r['counting_method']=='tracking_records_not_unique_physical_objects'
    r2=tools.execute('locate_object',{'target':'目标1'})
    assert r2['first_seen']==.2 and r2['last_seen']==1.8
    assert 'secret' not in str(r)+str(r2)
    other=media();other['targets']=[];other['counts']=[];other['evidence']=[];other['highlights']=[]
    assert MediaTools(other).execute('count_objects',{'label':'车辆'})['count']==0


def test_cross_media_citations_and_wrong_numeric_claim_are_rejected():
    from api.media_tools import MediaTools
    tools=MediaTools(media());r=tools.execute('count_objects',{'label':'汽车'})
    key=r['metrics'][0]['key']
    with pytest.raises(ValueError): tools.validate_answer({'answer':'有3辆车','evidence_ids':['own-1'],'claims':[{'key':key,'value':3}]})
    with pytest.raises(ValueError): tools.validate_answer({'answer':'有2辆车','evidence_ids':['other-upload-1'],'claims':[{'key':key,'value':2}]})
    valid=tools.validate_answer({'answer':'跟踪编号不代表唯一物理身份。','evidence_ids':['own-1'],'fact_keys':[key]})
    assert valid['citations'][0]['image_url'].startswith('/private/')


def test_visible_type_number_labels_can_be_used_for_appearance_queries():
    from api.media_tools import MediaTools
    tools=MediaTools(media())
    assert tools.execute('locate_object',{'target':'汽车 #1'})['first_seen']==.2
    assert tools.execute('locate_object',{'target':'#2'})['first_seen']==.6
    assert 'error' in tools.execute('locate_object',{'target':'1.2秒'})


def test_answer_cannot_turn_category_count_into_vehicle_count():
    from api.media_tools import MediaTools
    tools=MediaTools(media());r=tools.execute('count_objects',{'label':'汽车'})
    with pytest.raises(ValueError):
        tools.validate_answer({'answer':'识别到1辆汽车。','evidence_ids':['own-1'],'claims':[r['metrics'][0]]})
    for phrase in ('发现两艘船。','有一架飞机。','出现三台电视。','有两辆汽车。'):
        with pytest.raises(ValueError):
            tools.validate_answer({'answer':phrase,'evidence_ids':['own-1'],'fact_keys':[r['metrics'][0]['key']]})


def test_new_object_question_supplements_once_and_keeps_original_targets():
    from api.media_tools import MediaTools
    from copy import deepcopy
    scene=media();scene.update(classes=[2],class_labels=['car'],class_names=['汽车']);scene['labels']['dog']='狗'
    calls=[]
    def supplement(classes):
        calls.append(classes);updated=deepcopy(scene)
        updated.update(classes=[2,16],class_labels=['car','dog'],class_names=['汽车','狗'],revision=2)
        updated['targets'].append({'id':'3','name':'目标3','label':'dog','first_seen':0,'last_seen':1,'evidence_ids':['own-2']})
        updated['counts'].append({'label':'dog','name':'狗','count':1,'max_simultaneous':1})
        return updated
    tools=MediaTools(scene,supplement=supplement);result=tools.execute('count_objects',{'label':'狗'})
    assert result['count']==1 and calls==[[16]]
    assert tools.execute('count_objects',{'label':'狗'})['count']==1 and len(calls)==1
    assert [t['id'] for t in tools.scene['targets']]==['1','2','3']
    answer=tools.validate_answer({'answer':'跟踪编号不代表物理身份。','fact_keys':[result['metrics'][0]['key']],'evidence_ids':['own-2']})
    assert '1条狗' in answer['answer'] and '汽车、狗' in answer['answer']


def test_completed_class_counts_keep_the_selected_scope_in_the_final_answer():
    from api.media_tools import MediaTools
    scene=media();scene.update(classes=[2],class_labels=['car'],class_names=['汽车'])
    tools=MediaTools(scene);result=tools.execute('count_objects',{'label':'汽车'})
    answer=tools.validate_answer({'answer':'跟踪记录可能重复。','fact_keys':[result['metrics'][0]['key']],'evidence_ids':['own-1']})
    assert '已查找汽车' in answer['answer'] and result['count']==2


def test_supplement_failure_cannot_be_rendered_as_no_object_detected():
    from api.media_tools import MediaTools
    scene=media();scene.update(classes=[2],class_labels=['car'],class_names=['汽车']);scene['labels']['dog']='狗'
    def fail(_):raise RuntimeError('injected local worker failure')
    tools=MediaTools(scene,supplement=fail)
    with pytest.raises(ValueError):tools.execute('count_objects',{'label':'狗'})
    result=tools.validate_answer({'answer':'没有检测到狗。','evidence_ids':[],'fact_keys':[],'insufficient_evidence':True})
    assert '暂未完成' in result['answer'] and '没有检测到狗' not in result['answer']


def test_previous_aggregate_facts_are_recomputed_after_supplement():
    from api.media_tools import MediaTools
    from copy import deepcopy
    scene=media();scene.update(classes=[2],class_labels=['car'],class_names=['汽车']);scene['labels']['dog']='狗'
    def add(_):
        updated=deepcopy(scene);updated.update(classes=[2,16],class_labels=['car','dog'],class_names=['汽车','狗'],revision=2)
        updated['counts'].append({'label':'dog','name':'狗','count':1,'max_simultaneous':1})
        return updated
    tools=MediaTools(scene,supplement=add)
    before=tools.execute('count_objects',{'label':'全部'});key=before['metrics'][0]['key'];assert before['count']==2
    after=tools.execute('detect_objects',{'labels':['狗']})
    assert any(m['key']==key and m['value']==3 for m in after['metrics'])
    result=tools.validate_answer({'answer':'结果已补充。','evidence_ids':['own-1'],'fact_keys':[key]})
    assert result['factual_basis'][1]['value']==3


def test_success_for_cat_does_not_erase_failed_dog_notice():
    from api.media_tools import MediaTools
    from copy import deepcopy
    scene=media();scene.update(classes=[2],class_labels=['car'],class_names=['汽车']);scene['labels'].update(cat='猫',dog='狗')
    def add(ids):
        if ids==[16]:raise RuntimeError('dog run failed')
        updated=deepcopy(scene);updated.update(classes=[2,15],class_labels=['car','cat'],class_names=['汽车','猫'],revision=2)
        return updated
    tools=MediaTools(scene,supplement=add)
    with pytest.raises(ValueError):tools.execute('count_objects',{'label':'狗'})
    result=tools.execute('detect_objects',{'labels':['猫']})
    answer=tools.validate_answer({'answer':'没有检测到狗。','fact_keys':[result['metrics'][0]['key']],'evidence_ids':result['evidence_ids'],'insufficient_evidence':True})
    assert '查找狗暂未完成' in answer['answer'] and '没有检测到狗' not in answer['answer']


def test_each_question_cannot_add_four_classes_through_multiple_tool_calls():
    from api.media_tools import MediaTools
    from copy import deepcopy
    scene=media();scene.update(classes=[2],class_labels=['car'],class_names=['汽车']);scene['labels'].update(cat='猫',dog='狗',bird='鸟',horse='马')
    calls=[]
    def add(ids):
        calls.append(ids);updated=deepcopy(scene);updated.update(classes=[2,14,15,16],class_labels=['car','bird','cat','dog'],class_names=['汽车','鸟','猫','狗'],revision=2);return updated
    tools=MediaTools(scene,supplement=add)
    tools.execute('detect_objects',{'labels':['猫','狗','鸟']})
    with pytest.raises(ValueError):tools.execute('detect_objects',{'labels':['马']})
    assert len(calls)==1


def test_media_uses_real_graph_with_bound_tools_and_no_private_asset_urls_in_provider_context():
    import asyncio,json
    from api.agent import run_agent
    from api.config import Settings
    calls=[]
    async def provider(messages,schemas,force):
        calls.append(messages)
        assert all(s['function']['name'] in ('rank_objects','detect_objects','count_objects','locate_object','get_highlights','get_evidence') for s in schemas)
        if len(calls)==1:
            msg={'content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'count_objects','arguments':'{"label":"车辆"}'}}]}
        else:
            assert 'secret' not in json.dumps(messages)
            result=json.loads(messages[-1]['content'])
            msg={'content':json.dumps({'answer':'跟踪编号不代表唯一身份。','evidence_ids':['own-1'],'rule_ids':[],
                'fact_keys':[result['metrics'][0]['key']],'insufficient_evidence':False})}
        return {'choices':[{'message':msg}],'usage':{'prompt_tokens':20,'completion_tokens':10}}
    result=asyncio.run(run_agent(media(),'A',3,'有几辆车',[],Settings(),lambda _:None,provider=provider))
    assert '2条车辆的识别记录' in result['answer'] and '可能被重复标记' in result['answer']
    assert result['tool_calls'][0]['name']=='count_objects'
    assert result['usage']['model_calls']==2


@pytest.mark.parametrize('citation',['own-1','other-private-upload'])
def test_graph_keeps_verified_tool_facts_when_final_explanation_repeats_a_number(citation):
    import asyncio,json
    from api.agent import run_agent,AgentError
    from api.config import Settings
    calls=[]
    async def provider(messages,schemas,force):
        calls.append(messages)
        if len(calls)==1:
            msg={'content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'count_objects','arguments':'{"label":"汽车"}'}}]}
        else:
            msg={'content':json.dumps({'answer':'这里有99辆汽车。','fact_keys':['car.count'],
                'evidence_ids':[citation],'rule_ids':[],'insufficient_evidence':False})}
        return {'choices':[{'message':msg}],'usage':{'prompt_tokens':20,'completion_tokens':10}}
    task=run_agent(media(),'A',3,'有几辆汽车',[],Settings(),lambda _:None,provider=provider)
    if citation!='own-1':
        with pytest.raises(AgentError):asyncio.run(task)
        return
    result=asyncio.run(task)
    assert '2条汽车的识别记录' in result['answer'] and '可能被重复标记' in result['answer']
    assert '99' not in result['answer']
    assert result['usage']['model_calls']==3 and len(calls)==3
