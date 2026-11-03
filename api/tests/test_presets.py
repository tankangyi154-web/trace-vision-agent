from copy import deepcopy
import hashlib,json
from pathlib import Path
import pytest


def fixture_preset(root):
    directory=root/'web/public/media/presets/daylight';directory.mkdir(parents=True)
    assets={}
    for name in ['analysis-source.mp4','r1-annotated.webm','r1-evidence-0000.jpg']:
        content=('fixture-'+name).encode();(directory/name).write_bytes(content)
        assets[name]={'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
    evidence={'id':'preset-daylight-r1-e0','t':0.,'image':'r1-evidence-0000.jpg','track_id':'1','target_ids':['1'],'description':'actual fixture frame'}
    result={'id':'preset-daylight','data_kind':'uploaded_media','kind':'video','source_sha256':'a'*64,'cache_sha256':assets['analysis-source.mp4']['sha256'],
        'source_media':'analysis-source.mp4','cache_file':'analysis-source.mp4','media':'r1-annotated.webm','poster':evidence['image'],
        'evidence':[evidence],'highlights':[deepcopy(evidence)],'media_history':[],'classes':[0,2,1,9],'revision':1,'duration':1.,'sample_fps':5,
        'width':32,'height':32,'source_width':32,'source_height':32,'processed_frames':5,'max_simultaneous':1,'labels':{'person':'人'},
        'counts':[{'label':'person','name':'人','count':1,'max_simultaneous':1}],
        'frame_counts':[{'t':0.,'counts':{'person':1}}],
        'targets':[{'id':'1','label':'person','label_name':'人','name':'人 #1','first_seen':0.,'last_seen':0.,'evidence_ids':[evidence['id']],'samples':[{'t':0.,'bbox':[.1,.1,.8,.8]}]}]}
    data={'schema':1,'id':'daylight','title':'白天多物体','focus':'多类别','subtitle':'查看真实结果','version':'fixture-v1','duration':1.,'featured_target_id':'1',
        'source':{'title':'fixture','url':'https://example.com/source','author':'fixture','license':'fixture','license_url':'https://example.com/license'},'result':result,'assets':assets}
    (root/'data/presets').mkdir(parents=True)
    (root/'data/presets/daylight.json').write_text(json.dumps(data),encoding='utf8')
    return data


def test_prepared_examples_open_without_vision_environment_or_model_key(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from api.config import Settings
    from api.store import SQLiteStore
    from api.uploads import UploadService
    from api.index import create_app
    fixture_preset(tmp_path);monkeypatch.setattr('api.presets.ROOT',tmp_path)
    def no_inference(*args,**kwargs):raise AssertionError('Opening an example must not start a worker')
    monkeypatch.setattr(UploadService,'_run',no_inference)
    original=UploadService.__init__
    def initialize(self,*args,**kwargs):kwargs['directory']=tmp_path/'jobs';original(self,*args,**kwargs)
    monkeypatch.setattr(UploadService,'__init__',initialize)
    store=SQLiteStore(tmp_path/'state.db')
    with TestClient(create_app(Settings(),store)) as client:
        rows=client.get('/api/presets').json()['presets'];assert rows[0]['id']=='daylight'
        data=client.get('/api/presets/daylight').json()
        assert data['analysis_mode']=='precomputed' and data['external_model_calls_on_open']==0
        assert len(data['guides'])==3 and '首次识别于0秒' in data['guides'][2]['answer']
        assert client.get('/api/presets/unknown').status_code==404
        owner=client.post('/api/sessions').json()['session_id']
        headers={'X-Session-ID':owner}
        job=client.post('/api/presets/daylight/open',headers=headers).json()
        assert job['status']=='complete' and job['classes']==[0,2,1,9]
        again=client.post('/api/presets/daylight/open',headers=headers).json()
        assert again['id']==job['id'] and store.remaining(owner,5)==5
        assert job['result']['id']==job['scene_id']
        assert job['result']['evidence'][0]['id'].startswith(job['scene_id'])
        assert client.get('/api/uploads/'+job['id'],headers={'X-Session-ID':'x'*32}).status_code==404


def test_example_copy_rejects_changed_assets_and_does_not_share_writable_files(tmp_path):
    from api.presets import open_private_copy
    from api.uploads import UploadService,UploadError
    fixture_preset(tmp_path);service=UploadService(tmp_path/'jobs')
    public=tmp_path/'web/public/media/presets/daylight/analysis-source.mp4'
    job=open_private_copy(service,'daylight','owner',tmp_path)
    private=service._path(job['id'])/'analysis-source.mp4'
    private.write_bytes(b'private changed')
    assert public.read_bytes()!=private.read_bytes()
    public.write_bytes(b'corrupt')
    with pytest.raises(UploadError):open_private_copy(service,'daylight','another-owner',tmp_path)
    assert len(list(service.directory.glob('*/job.json')))==1
    service.close()


def test_packaged_examples_have_all_categories_real_evidence_and_honest_guides():
    from api.presets import list_presets,get_preset,load_preset
    from api.catalog import ROOT
    presets=list_presets();assert [r['id'] for r in presets]==['daylight','lowlight','occlusion']
    assert len(presets[0]['class_names'])>=6
    for preset in presets:
        raw=load_preset(preset['id']);data=get_preset(preset['id']);result=data['result']
        assert result['processed_frames']==len(result['frame_counts'])
        assert raw['preparation']['external_model_calls']==0
        for name,metadata in raw['assets'].items():
            path=ROOT/'web/public/media/presets'/preset['id']/name
            assert path.stat().st_size==metadata['bytes']
            with path.open('rb') as handle:assert hashlib.file_digest(handle,'sha256').hexdigest()==metadata['sha256']
        ids={row['id'] for row in result['evidence']}
        assert all(p['id'] in ids for guide in data['guides'] for p in guide['citations'])
    gap=next(g for g in get_preset('occlusion')['guides'] if g['id']=='gap')
    assert gap['target_id']=='30' and len(gap['citations'])==2 and '不能确认' in gap['answer']
