from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent


@lru_cache(maxsize=16)
def get_scene(scene_id: str) -> dict:
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',scene_id): raise KeyError(scene_id)
    path=ROOT/'data'/'scenes'/f'{scene_id}.json'
    if not path.is_file(): raise KeyError(scene_id)
    scene=json.loads(path.read_text(encoding='utf-8-sig'))
    if scene['data_kind']!='real_detection':
        raise ValueError('Development fixtures cannot be served as release scenes')
    return scene


def list_scenes():
    scenes=[]
    order={'harbor':0,'crossing':1,'night':2}
    for path in sorted((ROOT/'data'/'scenes').glob('*.json'),key=lambda p:(order.get(p.stem,99),p.stem)):
        scene=deepcopy(get_scene(path.stem))
        for track in scene['tracks']: track.pop('samples',None)
        scenes.append(scene)
    return scenes


def get_rules():
    return json.loads((ROOT/'data'/'rules.json').read_text(encoding='utf-8'))


def get_evaluation():
    path=ROOT/'evals'/'results.json'
    if not path.is_file():
        return {'status':'pending','measured':False,'summary':'真实视觉处理及标注评测尚未完成，不提供准确率。','metrics':[],'scenes':[],'failures':[]}
    return json.loads(path.read_text(encoding='utf-8-sig'))
