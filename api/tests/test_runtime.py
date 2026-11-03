import hashlib
import json
import sys

from api.runtime import inspect_runtime


def test_gpu_environment_requires_successful_smoke_test_and_cpu_falls_back(tmp_path):
    from api.runtime import vision_python
    gpu=tmp_path/'work/vision-gpu-env'
    executable=gpu/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    executable.parent.mkdir(parents=True);executable.write_bytes(b'fixture')
    assert 'vision-env' in str(vision_python(tmp_path))
    (gpu/'ready.json').write_text(json.dumps({'cuda_smoke_test':True}))
    assert vision_python(tmp_path)==executable
    (gpu/'ready.json').write_text('corrupt')
    assert 'vision-env' in str(vision_python(tmp_path))


def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr('api.runtime.shutil.which', lambda _: None)
    executable = tmp_path / 'work/vision-env' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'fixture-runtime')
    weights = tmp_path / 'vision/weights/yolo11s.pt'
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b'verified-fixture-model')
    (tmp_path / 'vision/upload-model.lock.json').write_text(json.dumps({'model':'yolo11s.pt','sha256': hashlib.sha256(weights.read_bytes()).hexdigest()}))
    appearance=tmp_path/'vision/weights/osnet.pth';appearance.write_bytes(b'appearance')
    (tmp_path/'vision/appearance-model.lock.json').write_text(json.dumps({'model':'osnet.pth','sha256':hashlib.sha256(b'appearance').hexdigest()}))
    return weights


def test_corrupt_model_is_not_reported_as_ready(tmp_path, monkeypatch):
    weights = prepared(tmp_path, monkeypatch)
    assert inspect_runtime(tmp_path)['image_analysis']
    weights.write_bytes(b'corrupted')
    status = inspect_runtime(tmp_path)
    assert not status['image_analysis'] and not status['video_analysis']
    assert 'verified_model' in status['missing']
    assert str(tmp_path) not in json.dumps(status)


def test_missing_video_encoder_does_not_disable_image_analysis(tmp_path, monkeypatch):
    prepared(tmp_path, monkeypatch)
    status = inspect_runtime(tmp_path)
    assert status['image_analysis'] and not status['video_analysis']
    encoder = tmp_path / 'work/bin' / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
    encoder.parent.mkdir(parents=True)
    encoder.write_bytes(b'fixture-encoder')
    assert inspect_runtime(tmp_path)['video_analysis']
    assert not inspect_runtime(tmp_path, local_allowed=False)['image_analysis']


def test_unverified_appearance_disables_video_but_keeps_image_detection(tmp_path,monkeypatch):
    prepared(tmp_path,monkeypatch)
    (tmp_path/'vision/weights/osnet.pth').write_bytes(b'corrupt')
    status=inspect_runtime(tmp_path)
    assert status['image_analysis'] and not status['video_analysis'] and not status['appearance_tracking']
    assert 'verified_appearance_model' in status['missing']


def test_failed_native_self_test_closes_upload_capability_but_can_be_rerun(tmp_path,monkeypatch):
    prepared(tmp_path,monkeypatch)
    (tmp_path/'work/vision-selftest.json').write_text(json.dumps({'ok':False,'code':'native_runtime'}))
    status=inspect_runtime(tmp_path)
    assert not status['image_analysis'] and 'native_runtime' in status['missing']
    assert inspect_runtime(tmp_path,check_self_test=False)['image_analysis']
    (tmp_path/'work/vision-selftest.json').write_text(json.dumps({'ok':True}))
    assert inspect_runtime(tmp_path)['image_analysis']


def test_local_store_can_persist_outside_the_installed_runtime(tmp_path,monkeypatch):
    from api.config import Settings
    monkeypatch.setenv('TRACE_LOCAL_STATE_DIR',str(tmp_path/'state'))
    store=Settings().store()
    assert store.path==str(tmp_path/'state/local.sqlite3')
    assert store.create_session()
