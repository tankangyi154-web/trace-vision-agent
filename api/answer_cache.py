"""Private per-record response reuse, invalidated by code, source and context."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from api.media_plan import build_plan


@lru_cache(maxsize=1)
def implementation_version():
    root=Path(__file__).resolve().parent
    paths=[root/name for name in ('agent.py','media_tools.py','media_profile.py','media_plan.py','media_answer.py','visual_estimates.py','target_frames.py')]
    paths.append(root.parent/'vision/target_frames.py')
    return hashlib.sha256(b''.join(path.read_bytes() for path in paths)).hexdigest()


def answer_cache_key(scene,question,selected,history,settings):
    plan=build_plan(question,scene,selected,history)
    data={'version':implementation_version(),'source':scene.get('cache_sha256',scene.get('source_sha256')),'revision':scene.get('revision'),
        'question':question.strip(),'selected':selected,'tasks':plan['tasks'],
        'provider':settings.provider,'model':settings.model,'endpoint':settings.base_url,
        'unknown_history':history if plan.get('needs_planning') else None}
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
