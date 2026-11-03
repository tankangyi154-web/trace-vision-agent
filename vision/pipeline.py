"""Conservative result cache identity, independent of user data or absolute paths."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=('vision/analyze_media.py','vision/media_scope.py','vision/media_detection.py','vision/media_tracking.py',
       'vision/appearance.py','vision/appearance_tracker.py','vision/annotation.py','vision/onnx_cpu.py',
       'vision/cpu_calibration.py','vision/upload-model.lock.json','vision/appearance-model.lock.json',
       'vision/upload-tracking.json','vision/upload-detection.json','vision/bytetrack.yaml','data/media-limits.json','data/annotation-style.json',
       'work/onnx-models/manifest.json')
def pipeline_fingerprint(root=None):
    root=Path(root or ROOT);digest=hashlib.sha256()
    for name in FILES:
        path=root/name;digest.update(name.encode());digest.update(path.read_bytes() if path.is_file() else b'<missing>')
    return digest.hexdigest()
