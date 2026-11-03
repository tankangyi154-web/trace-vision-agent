import hashlib
import json
from types import SimpleNamespace
import pytest
from api.uploads import UploadService,UploadError


def test_target_cards_are_owner_scoped_cached_hash_checked_and_private(tmp_path,monkeypatch):
    service=UploadService(tmp_path/'jobs');public=service.reserve('owned-session','photo.jpg',100,classes=[0])
    job=service._read(public['id']);directory=service._path(job['id'])
    box=[.1,.1,.4,.9]
    data={'revision':1,'kind':'image','sample_fps':0,'source_sha256':'input-hash','cache_sha256':'cache-hash',
          'media':'r1-annotated.jpg','poster':'poster.jpg','source_media':'analysis-source.png',
          'targets':[{'id':'30','samples':[{'t':0,'bbox':box}]}],'evidence':[],'highlights':[]}
    job.update(status='complete',result=data);service._write(job)
    calls=[]
    monkeypatch.setenv('DEEPSEEK_API_KEY','must-not-reach-extractor')
    def extractor(arguments,**kwargs):
        calls.append(arguments)
        assert 'DEEPSEEK_API_KEY' not in kwargs['env']
        request=json.loads(__import__('pathlib').Path(arguments[-1]).read_text(encoding='utf8'))
        assert 'owned-session' not in json.dumps(request)
        assert request['target']=='30'
        name=f"view-r1-t30-f0-{request['key']}.jpg";image=b'\xff\xd8mocked-worker-jpeg\xff\xd9'
        (directory/name).write_bytes(image)
        manifest={'target':'30','revision':1,'cache_sha256':'cache-hash','frames':[{'t':0,'bbox':box,'pixels':[100,400],
                  'image':name,'sha256':hashlib.sha256(image).hexdigest()}]}
        (directory/request['manifest']).write_text(json.dumps(manifest),encoding='utf8')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('api.target_frames.subprocess.run',extractor)
    with pytest.raises(UploadError):service.inspect_target(job['scene_id'],'wrong-owner','30')
    assert calls==[]
    bundle=service.inspect_target(job['scene_id'],'owned-session','30')
    assert len(calls)==1 and bundle['images'][0].startswith('data:image/jpeg;base64,')
    assert 'base64' not in json.dumps(bundle['scene'])
    evidence=bundle['scene']['evidence'][-1]
    assert evidence['track_id']=='30' and 'token=' in evidence['image_url']
    name=evidence['image_url'].split('/assets/')[1].split('?')[0]
    assert service.asset(job['id'],name,job['asset_token']).is_file()
    with pytest.raises(UploadError):service.asset(job['id'],name,'wrong-token')
    service.inspect_target(job['scene_id'],'owned-session','30')
    assert len(calls)==1
    (directory/name).write_bytes(b'altered-image')
    with pytest.raises(ValueError):service.inspect_target(job['scene_id'],'owned-session','30')
    service.delete(job['id'],'owned-session');assert not directory.exists();service.close()
