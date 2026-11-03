"""Case-specific temporal evidence and independent claim checking. No vision imports."""
from copy import deepcopy
import hashlib
import math
import re
from api.catalog import ROOT
from api.domain import analyze, evidence_near

CASE_ID='harbor-T001-gap'
SOURCE_SHA='48acaf2024ca892a133c31b238742f8f76d6cef76188e33dc01904e15a600376'
FRAME_RANGE=tuple(range(124,131))
TRACK_ID='T001'


def scene_version():
    return hashlib.sha256((ROOT/'data/scenes/harbor.json').read_bytes()).hexdigest()


def baseline_facts(scene,threshold):
    result=analyze(scene,'A',threshold)
    dwell=next(d for d in result['dwell'] if d['track_id']==TRACK_ID)
    intervals=dwell['intervals']
    longest=round(max((i['end']-i['start'] for i in intervals),default=0),3)
    longest_record=max(intervals,key=lambda i:i['end']-i['start'])
    gaps=[{'start':e['start'],'end':e['end'],'duration':e['duration']} for e in result['events'] if e['track_id']==TRACK_ID and e['type']=='observation_gap']
    evidence=[]
    for interval in intervals:
        for t in (interval['start'],interval['end']): evidence+=evidence_near(scene,TRACK_ID,t)
    supported=longest+1e-8>=threshold
    return {'observed_seconds':dwell['observed_seconds'],'longest_interval_seconds':longest,
            'longest_interval':{**deepcopy(longest_record),'duration':longest},
            'span_seconds':round(intervals[-1]['end']-intervals[0]['start'],3),
            'intervals':deepcopy(intervals),'gaps':gaps,'gap_seconds':round(sum(g['duration'] for g in gaps),3),
            'threshold_seconds':threshold,'policy_gap_seconds':.5,
            'verdict':'supported_by_observations' if supported else 'insufficient_evidence',
            'description':f"按0.5秒容忍规则，最长区间{longest:g}秒；"+('观测支持所选阈值，但不证明物理身份或地理驻留。' if supported else '证据不足以确认达到所选连续阈值，不等于确认未发生。'),
            'evidence_ids':list(dict.fromkeys(evidence)),
            'unknown_frames':list(FRAME_RANGE),'missing_evidence_times':[f/10 for f in FRAME_RANGE]}


def merge_review(scene,review,review_id):
    """Build a separate hypothesis snapshot using only accepted actual detections."""
    updated=deepcopy(scene)
    track=next(t for t in updated['tracks'] if t['id']==TRACK_ID)
    existing={s['frame'] for s in track['samples']}
    frames={f['frame']:f for f in review['frames']}
    seen=set()
    for obs in review['observations']:
        f=obs['frame']
        if f not in FRAME_RANGE or f in seen or f in existing or abs(obs['t']-f/scene['fps'])>1e-6:
            raise ValueError('Review contains an invalid or duplicated frame/time')
        if not frames.get(f,{}).get('accepted') or obs.get('source')!='review' or obs.get('association')!='geometric_candidate':
            raise ValueError('Only accepted actual detections can be merged')
        bbox=obs['bbox']
        if len(bbox)!=4 or not all(math.isfinite(v) and 0<=v<=1 for v in bbox) or not bbox[0]<bbox[2] or not bbox[1]<bbox[3]:
            raise ValueError('Invalid review coordinates')
        confidence=obs['confidence']
        if not math.isfinite(confidence) or not .25<=confidence<=1: raise ValueError('Invalid confidence')
        track['samples'].append({k:deepcopy(obs[k]) for k in ('frame','t','bbox','confidence')})
        seen.add(f)
    track['samples'].sort(key=lambda s:s['t'])
    for f in review['frames']:
        updated['evidence'].append({'id':f"review-{review_id}-f{f['frame']:04d}",'track_id':TRACK_ID,
             't':f['t'],'image_url':f['overlay_image'],
             'description':f"本地ROI复检帧{f['frame']}，{'通过几何候选门控' if f['accepted'] else '关联未确认'}；不是身份或物理连续证明"})
    return updated


def review_facts(updated,review,threshold):
    result=baseline_facts(updated,threshold)
    unresolved=[f['frame'] for f in review['frames'] if not f['accepted']]
    result['unknown_frames']=unresolved
    result['missing_evidence_times']=[f/10 for f in unresolved]
    result['reviewed_frames']=len(review['frames'])
    result['accepted_frames']=len(review['observations'])
    result['unresolved_frames']=len(unresolved)
    # The unmodified baseline already supports 3s. A new bridge through unresolved
    # review frames cannot establish a larger continuous claim solely by tolerance.
    original=deepcopy(updated)
    target=next(t for t in original['tracks'] if t['id']==TRACK_ID)
    target['samples']=[s for s in target['samples'] if s['frame'] not in FRAME_RANGE]
    before=baseline_facts(original,threshold)
    supported=result['longest_interval_seconds']+1e-8>=threshold and (not unresolved or before['verdict']=='supported_by_observations')
    result['verdict']='supported_by_observations' if supported else 'insufficient_evidence'
    result['description']=(f"接受{len(review['observations'])}/7帧为几何候选，规则合并最长区间{result['longest_interval_seconds']:g}秒；"
        +(f"仍有{len(unresolved)}帧未解。" if unresolved else '本窗口逐帧均有几何候选。')
        +('已知观测支持当前阈值；关联仍是几何假设，不证明物理身份。' if supported else '不能把容忍规则合并区间当作无缺证据的物理连续确认。'))
    return result


def validate_claims(obj,before,after):
    allowed=('observed_seconds','longest_interval_seconds','span_seconds','gap_seconds','threshold_seconds','unresolved_frames','accepted_frames')
    checks=[]
    claims=obj.get('claims')
    if not isinstance(claims,list) or not 1<=len(claims)<=16:
        return {'status':'rejected','claims':[],'submitted_claim_count':len(claims) if isinstance(claims,list) else None,
                'description':'需要1—16条结构化数值结论，不能缺失或超出有界核验容量。'}
    for claim in claims:
        if not isinstance(claim,dict):
            checks.append({'metric':'invalid','value':None,'expected':None,'passed':False,'description':'结论格式无效'}); continue
        metric=claim.get('metric'); basis=claim.get('basis')
        facts=before if basis=='baseline' else after if basis=='review' else None
        expected=facts.get(metric) if facts is not None and metric in allowed else None
        value=claim.get('value')
        passed=type(value) in (int,float) and math.isfinite(value) and expected is not None and abs(value-expected)<.001
        checks.append({'metric':str(metric),'basis':basis,'value':value if type(value) in (int,float) and math.isfinite(value) else None,
                       'expected':expected,'passed':passed,'description':'与源观测独立复算一致' if passed else '数值、指标口径或证据版本不匹配'})
    # Fixed-case arithmetic guard for an explicit "D seconds (S-E seconds)".
    # It is intentionally not presented as a general proof of natural language.
    pattern=r'(\d+(?:\.\d+)?)\s*秒\s*[（(]\s*(\d+(?:\.\d+)?)\s*(?:—|–|-|~|～|至|到)\s*(\d+(?:\.\d+)?)\s*秒?\s*[）)]'
    for match in re.finditer(pattern,obj.get('answer','')):
        duration,start,end=map(float,match.groups());expected=round(end-start,3)
        checks.append({'metric':'temporal_text_range','basis':'answer','value':duration,'expected':expected,
                       'passed':abs(duration-expected)<.001,'description':'显式时长与括号内起止时间相符' if abs(duration-expected)<.001 else '自由文本时长与所附时间区间矛盾，未采纳该回答'})
    final_basis=obj.get('basis','review' if after is not None else 'baseline')
    facts=after if final_basis=='review' else before if final_basis=='baseline' else None
    verdict=facts['verdict'] if facts else None
    matched=verdict is not None and obj.get('conclusion')==verdict
    checks.append({'metric':'conclusion','value':None,'expected':None,'passed':matched,
                   'description':'观测支持程度与证据完整性一致' if matched else '最终结论越过了观测/缺帧证据所能支持的范围'})
    status='rejected' if not all(c['passed'] for c in checks) else 'insufficient_evidence' if verdict=='insufficient_evidence' else 'passed'
    return {'status':status,'claims':checks,'description':'结构化数值与结论经过程序复算；不等于模型自由文本已完全证明。'}
