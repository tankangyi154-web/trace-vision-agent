"""Check a local result against the narrowly scoped red-pedestrian checkpoints."""
import argparse,json
from pathlib import Path

def iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union else 0

def check(result,truth):
    if result.get('source_sha256')!=truth['source_sha256']:raise ValueError('This checkpoint set belongs to a different source video.')
    timeline=[]
    for point in truth['red_reference_boxes']:
        candidates=[(iou(sample['bbox'],point['bbox']),target['id']) for target in result['targets'] if target['label']=='person' for sample in target['samples'] if abs(sample['t']-point['t'])<.001]
        match=max(candidates) if candidates else (0,None)
        timeline.append({'t':point['t'],'id':match[1] if match[0]>=.5 else None})
    anchor=timeline[0]['id'];false_links=[]
    for point in truth['beige_reference_boxes']:
        sample=next((s for target in result['targets'] if target['id']==anchor for s in target['samples'] if abs(s['t']-point['t'])<.001),None)
        if sample and iou(sample['bbox'],point['bbox'])>=.5:false_links.append(point['t'])
    return {'passed':bool(anchor) and all(p['id']==anchor for p in timeline) and not false_links,
        'scope':'Known crossing spot check only; not a general tracking score.','timeline':timeline,'false_continuations_to_beige':false_links}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--truth',type=Path,default=Path(__file__).with_name('tracking-stability-spotcheck.json'))
    args=parser.parse_args();report=check(json.loads(args.result.read_text(encoding='utf8')),json.loads(args.truth.read_text(encoding='utf8')))
    print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if report['passed'] else 1)
