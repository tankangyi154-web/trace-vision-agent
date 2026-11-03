"""Restore the pinned official YOLO11n asset, including a corrupted local cache."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def ensure_model(root=ROOT, lock_name='model.lock.json'):
    lock = json.loads((Path(root) / 'vision' / lock_name).read_text(encoding='utf-8'))
    path = Path(root) / 'vision/weights' / lock['model']
    if path.is_file() and digest(path) == lock['sha256']:
        return lock
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pt.download')
    print('Preparing verified official model (missing or invalid local cache).')
    try:
        with urllib.request.urlopen(lock.get('url',URL), timeout=90) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if digest(temporary) != lock['sha256']:
            raise RuntimeError('Downloaded model does not match the pinned SHA-256; cached file was not replaced.')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return lock


if __name__ == '__main__':
    for lock_name in ('model.lock.json','upload-model.lock.json','appearance-model.lock.json'):
        artifact = ensure_model(lock_name=lock_name)
        print(f'Verified {artifact["model"]}: {artifact["sha256"]}')
