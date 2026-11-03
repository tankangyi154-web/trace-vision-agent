import hashlib
import io
import json
import pytest

from vision.download_model import ensure_model


def fixture_model(tmp_path):
    weights = tmp_path / 'vision/weights/yolo11n.pt'
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b'corrupt-cache')
    (tmp_path / 'vision/model.lock.json').write_text(json.dumps({'model': 'yolo11n.pt', 'sha256': hashlib.sha256(b'verified').hexdigest()}))
    return weights


def test_invalid_cache_is_replaced_only_after_verified_download(tmp_path, monkeypatch):
    weights = fixture_model(tmp_path)
    monkeypatch.setattr('vision.download_model.urllib.request.urlopen', lambda *args, **kwargs: io.BytesIO(b'verified'))
    ensure_model(tmp_path)
    assert weights.read_bytes() == b'verified'


def test_mismatched_download_never_replaces_cached_file(tmp_path, monkeypatch):
    weights = fixture_model(tmp_path)
    monkeypatch.setattr('vision.download_model.urllib.request.urlopen', lambda *args, **kwargs: io.BytesIO(b'wrong-download'))
    with pytest.raises(RuntimeError, match='SHA-256'):
        ensure_model(tmp_path)
    assert weights.read_bytes() == b'corrupt-cache'
    assert not weights.with_suffix('.pt.download').exists()


def test_upload_model_has_its_own_pinned_asset_and_does_not_replace_demo_model(tmp_path,monkeypatch):
    demo=fixture_model(tmp_path)
    lock={'model':'yolo11s.pt','sha256':hashlib.sha256(b'upload-model').hexdigest(),'url':'https://example.test/pinned-upload.pt'}
    (tmp_path/'vision/upload-model.lock.json').write_text(json.dumps(lock))
    urls=[]
    def fetch(url,**kwargs):urls.append(url);return io.BytesIO(b'upload-model')
    monkeypatch.setattr('vision.download_model.urllib.request.urlopen',fetch)
    ensure_model(tmp_path,'upload-model.lock.json')
    assert urls==[lock['url']]
    assert (tmp_path/'vision/weights/yolo11s.pt').read_bytes()==b'upload-model'
    assert demo.read_bytes()==b'corrupt-cache'
