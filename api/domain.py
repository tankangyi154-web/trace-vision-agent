"""Deterministic geometry and clip-relative event statistics. No model calls."""
from __future__ import annotations
import math
import hashlib
import json

RULES_VERSION = 'zones-v2-scoped'


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[(i + 1) % len(polygon)]
        cross = (x-ax)*(by-ay)-(y-ay)*(bx-ax)
        if abs(cross) < 1e-10 and min(ax,bx)-1e-10 <= x <= max(ax,bx)+1e-10 and min(ay,by)-1e-10 <= y <= max(ay,by)+1e-10:
            return True
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            inside = not inside
    return inside


def evidence_near(scene, track_id, t):
    available = [e for e in scene['evidence'] if e['track_id'] == track_id]
    return [min(available, key=lambda e: abs(e['t']-t))['id']] if available else []


def analyze(scene: dict, zone_id: str, dwell_seconds: float) -> dict:
    zone = next((z for z in scene['zones'] if z['id'] == zone_id), None)
    if not zone or not math.isfinite(dwell_seconds) or not 0 < dwell_seconds <= 120:
        raise ValueError('Unknown zone or invalid dwell threshold')
    gap = max(.5, 2 / scene['processing']['sample_fps'])
    events, dwell = [], []

    def emit(track, kind, start, end, description, censored=False):
        events.append({
            'id': f"{scene['id']}:{zone_id}:{track['id']}:{kind}:{start:.3f}",
            'type': kind, 'track_id': track['id'], 'label': track['label'], 'zone_id': zone_id,
            'start': round(start,3), 'end': round(end,3), 'duration': round(end-start,3),
            'evidence_ids': evidence_near(scene,track['id'],start),
            'description': description, 'censored': censored,
        })

    for track in scene['tracks']:
        samples = sorted(track['samples'], key=lambda s:s['t'])
        prev, prev_inside, current = None, False, None
        intervals = []

        def close(censored):
            nonlocal current
            if current is None: return
            current['censored'] = censored
            intervals.append(current)
            if current['end'] - current['start'] + 1e-9 >= dwell_seconds:
                emit(track,'dwell',current['start'],current['end'],
                     f"区域{zone_id}内连续可观测驻留达到{dwell_seconds:g}秒",censored)
            current = None

        for sample in samples:
            t = sample['t']
            x1,y1,x2,y2 = sample['bbox']
            is_inside = point_in_polygon(((x1+x2)/2,(y1+y2)/2),zone['polygon'])
            continuous = prev is not None and 0 < t-prev['t'] <= gap + 1e-8
            if prev is not None and not continuous:
                close(True)
                if prev_inside or is_inside:
                    emit(track,'observation_gap',prev['t'],t,'所选区域的观测存在中断；无法仅凭漏检确认物理遮挡或进出时刻')
            if is_inside:
                if current is None:
                    current = {'start':round(t,3),'end':round(t,3),'censored':False}
                    if continuous and not prev_inside:
                        emit(track,'enter',t,t,f'观察到目标进入区域{zone_id}')
                    else:
                        emit(track,'initial_presence',t,t,'首次或恢复观测时已在区域内；进入时刻未知')
                elif continuous:
                    current['end'] = round(t,3)
            elif current is not None:
                close(False)
                if continuous and prev_inside:
                    emit(track,'exit',t,t,f'观察到目标离开区域{zone_id}')
            prev, prev_inside = sample, is_inside
        close(True)
        if intervals:
            observed = round(sum(i['end']-i['start'] for i in intervals),3)
            dwell.append({'track_id':track['id'],'label':track['label'],
                          'observed_seconds':observed,'intervals':intervals,
                          'evidence_ids':evidence_near(scene,track['id'],intervals[0]['start'])})
    dwell.sort(key=lambda d:(-d['observed_seconds'],d['track_id']))
    priority = {'initial_presence':0,'enter':1,'dwell':2,'exit':3,'observation_gap':4}
    events.sort(key=lambda e:(e['start'],e['track_id'],priority[e['type']]))
    revision={'scene_id':scene['id'],'source':scene['processing'].get('output_sha256'),
              'sample_fps':scene['processing']['sample_fps'],'duration':scene['duration'],
              'model_sha256':scene['processing'].get('model_sha256'),'tracker_sha256':scene['processing'].get('tracker_sha256'),
              'zone':zone,'tracks':scene['tracks'],'threshold':float(dwell_seconds),'rules_version':RULES_VERSION}
    scope_id=hashlib.sha256(json.dumps(revision,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'scene_id':scene['id'],'zone_id':zone_id,'dwell_seconds':dwell_seconds,'review_scope_id':scope_id,
            'events':events,'dwell':dwell,'evidence':scene['evidence'],
            'summary':{'tracks':len(dwell),'clip_tracks':len(scene['tracks']),
                       'entries':sum(e['type']=='enter' for e in events),
                       'dwell_alerts':sum(e['type']=='dwell' for e in events),
                       'observation_gaps':sum(e['type']=='observation_gap' for e in events)},
            'rules_version':RULES_VERSION}
