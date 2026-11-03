"""Read-only preparation checks. Health checks never import Torch or expose secrets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys


def vision_python(root: Path) -> Path:
    """Prefer an explicitly smoke-tested GPU environment, without importing Torch in HTTP."""
    root = Path(root)
    executable = 'Scripts/python.exe' if sys.platform == 'win32' else 'bin/python'
    gpu = root / 'work/vision-gpu-env'
    try:
        ready = json.loads((gpu / 'ready.json').read_text(encoding='utf8'))
        if isinstance(ready,dict) and ready.get('cuda_smoke_test') is True and (gpu / executable).is_file():
            return gpu / executable
    except (OSError, ValueError):
        pass
    return root / 'work/vision-env' / executable


def inspect_runtime(root: Path, *, local_allowed: bool = True, check_self_test: bool = True) -> dict:
    root = Path(root)
    python = vision_python(root)
    try:
        lock = json.loads((root / 'vision/upload-model.lock.json').read_text(encoding='utf-8'))
        expected = lock['sha256']
        model = root / 'vision/weights' / lock['model']
        model_ready = hashlib.sha256(model.read_bytes()).hexdigest() == expected
    except (OSError, ValueError, KeyError, TypeError):
        model_ready = False
    try:
        appearance=json.loads((root/'vision/appearance-model.lock.json').read_text(encoding='utf8'))
        appearance_ready=hashlib.sha256((root/'vision/weights'/appearance['model']).read_bytes()).hexdigest()==appearance['sha256']
    except (OSError,ValueError,KeyError,TypeError):appearance_ready=False
    ffmpeg = root / 'work/bin' / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
    python_ready = python.is_file()
    ffmpeg_ready = ffmpeg.is_file() or bool(shutil.which('ffmpeg'))
    self_test_ok=True;self_test_code=None
    if check_self_test and python.parent.parent.name!='vision-gpu-env':
        try:
            check=json.loads((root/'work/vision-selftest.json').read_text(encoding='utf8'))
            if check.get('ok') is False:self_test_ok=False;self_test_code=check.get('code','vision_self_test')
        except (OSError,ValueError,AttributeError):pass
    missing = [name for name, ready in (
        ('vision_runtime', python_ready), ('verified_model', model_ready), ('verified_appearance_model',appearance_ready), ('ffmpeg', ffmpeg_ready)
    ) if not ready]
    if not self_test_ok:missing.append(self_test_code)
    return {
        'local_uploads': local_allowed,
        'image_analysis': local_allowed and python_ready and model_ready and self_test_ok,
        'video_analysis': local_allowed and python_ready and model_ready and appearance_ready and ffmpeg_ready and self_test_ok,
        'appearance_tracking':local_allowed and appearance_ready,
        'model_verified': model_ready,
        'missing': missing if local_allowed else [],
    }
