"""Select actual target observations and make context/crop cards. No model or secrets."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4


def candidates(samples,limit=18):
    if len(samples)<=limit:return samples
    indices={round(i*(len(samples)-1)/(limit-5)) for i in range(limit-4)}
    indices.update(sorted(range(len(samples)),key=lambda i:(samples[i]['bbox'][2]-samples[i]['bbox'][0])*(samples[i]['bbox'][3]-samples[i]['bbox'][1]),reverse=True)[:2])
    complete=[i for i,s in enumerate(samples) if min(s['bbox'][0],s['bbox'][1],1-s['bbox'][2],1-s['bbox'][3])>=.015]
    indices.update(sorted(complete,key=lambda i:(samples[i]['bbox'][2]-samples[i]['bbox'][0])*(samples[i]['bbox'][3]-samples[i]['bbox'][1]),reverse=True)[:2])
    return [samples[i] for i in sorted(indices)]


def occlusion(box,others):
    area=(box[2]-box[0])*(box[3]-box[1])
    return max((max(0,min(box[2],b[2])-max(box[0],b[0]))*max(0,min(box[3],b[3])-max(box[1],b[1]))/area for b in others),default=0)


def select_frames(rows,purposes=()):
    if len(rows)<=3:return sorted(rows,key=lambda r:r['t'])
    first,last=min(r['t'] for r in rows),max(r['t'] for r in rows)
    selected=[]
    if 'body' in purposes:
        selected.append(max(rows,key=lambda r:r['score']+(3 if 'touching_frame_edge' not in r.get('flags',[]) else -2)-r.get('overlap',0)))
    if 'motion' in purposes:
        for edge in (0,2):
            group=[r for r in rows if min(2,int(3*(r['t']-first)/max(.001,last-first)))==edge]
            if group:
                best=max(group,key=lambda r:r['score'])
                if all(best is not row for row in selected):selected.append(best)
    if 'detail' in purposes:
        best=max(rows,key=lambda r:r['score'])
        if all(best is not row for row in selected) and len(selected)<3:selected.append(best)
    for sector in range(3):
        group=[r for r in rows if min(2,int(3*(r['t']-first)/max(.001,last-first)))==sector]
        if group:
            best=max(group,key=lambda r:r['score'])
            if all(best is not row for row in selected) and len(selected)<3:selected.append(best)
    return sorted(selected,key=lambda r:r['t'])


def make_cards(request_path):
    import cv2
    import numpy as np
    request_path=Path(request_path).resolve();directory=request_path.parent
    request=json.loads(request_path.read_text(encoding='utf8'))
    purposes=request.get('purposes',[])
    if not isinstance(purposes,list) or any(p not in ('body','motion','detail') for p in purposes):raise ValueError('purpose')
    ident=request['target'];revision=request['revision'];key=request['key']
    if not ident.isdecimal() or not isinstance(revision,int) or revision<1:raise ValueError('target')
    data=json.loads((directory/f'result-r{revision}.json').read_text(encoding='utf8'))
    source=directory/('analysis-source.png' if data['kind']=='image' else 'analysis-source.mp4')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=request['cache_sha256']:raise ValueError('source')
    target=next(t for t in data['targets'] if t['id']==ident)
    samples=sorted(target['samples'],key=lambda s:s['t'])
    fps=data['sample_fps'];others={}
    for item in data['targets']:
        if item['id']!=ident:
            for sample in item['samples']:others.setdefault(sample['t'],[]).append(sample['bbox'])
    cap=cv2.VideoCapture(str(source)) if data['kind']=='video' else None
    still=cv2.imread(str(source)) if cap is None else None
    rows=[]
    try:
        for sample in candidates(samples):
            if cap:
                index=round(sample['t']*fps)
                if abs(index/fps-sample['t'])>.001:continue
                cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,frame=cap.read()
                if not ok or abs(cap.get(cv2.CAP_PROP_POS_FRAMES)-(index+1))>.01:continue
            else:frame=still
            if frame is None:continue
            h,w=frame.shape[:2];box=sample['bbox']
            x1,y1=max(0,int(box[0]*w)),max(0,int(box[1]*h))
            x2,y2=min(w,math.ceil(box[2]*w)),min(h,math.ceil(box[3]*h))
            if x2<=x1 or y2<=y1:continue
            crop=frame[y1:y2,x1:x2]
            sharpness=float(cv2.Laplacian(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
            overlap=occlusion(box,others.get(sample['t'],[]))
            flags=[]
            if y2-y1<80:flags.append('small_target')
            if sharpness<35:flags.append('blurred')
            if overlap>.25:flags.append('overlapping_boxes')
            if min(box[0],box[1],1-box[2],1-box[3])<.01:flags.append('touching_frame_edge')
            score=.4*math.log(crop.size+1)+.35*min(7,math.log(sharpness+1))+.2*sample.get('confidence',0)-2*overlap
            torso=crop[max(0,int(crop.shape[0]*.2)):max(1,int(crop.shape[0]*.6))]
            hsv=cv2.cvtColor(torso,cv2.COLOR_BGR2HSV)
            signature=cv2.calcHist([hsv],[0,1],None,[12,4],[0,180,0,256]).ravel()
            signature=signature/max(float(signature.sum()),1)
            rows.append({'t':sample['t'],'bbox':box,'pixels':[x2-x1,y2-y1],'sharpness':round(sharpness,2),'overlap':round(overlap,3),
                         'flags':flags,'score':score,'frame':frame,'rect':[x1,y1,x2,y2],'signature':signature})
    finally:
        if cap:cap.release()
    chosen=select_frames(rows,purposes)
    if not chosen:raise ValueError('no_frames')
    clean=[r for r in chosen if r['pixels'][1]>=180 and not set(r['flags'])&{'blurred','overlapping_boxes','touching_frame_edge'}]
    distance=max((math.sqrt(max(0,1-float(np.sqrt(a['signature']*b['signature']).sum()))) for i,a in enumerate(clean) for b in clean[i+1:]),default=0)
    consistency={'status':'needs_review' if distance>.75 else 'no_strong_change_detected','color_distance':round(distance,3),
        'note':'同编号的清晰画面外观差异较大，请先核对是否发生编号混淆。' if distance>.75 else '未检出强烈色彩变化，不代表已证明真实身份相同。'}
    frames=[]
    for row in chosen:
        row.pop('signature',None)
        frame=row.pop('frame');x1,y1,x2,y2=row.pop('rect');h,w=frame.shape[:2]
        # Plain resizing only: the model also receives the actual source pixel size.
        card=np.full((600,1024,3),248,dtype=np.uint8)
        cv2.putText(card,f"Target #{ident} | {row['t']:g}s",(18,29),cv2.FONT_HERSHEY_SIMPLEX,.7,(35,45,60),2)
        scale=min(640/w,500/h);fw,fh=round(w*scale),round(h*scale)
        ox,oy=12+(640-fw)//2,55+(500-fh)//2
        card[oy:oy+fh,ox:ox+fw]=cv2.resize(frame,(fw,fh))
        cv2.rectangle(card,(ox+round(x1*scale),oy+round(y1*scale)),(ox+round(x2*scale),oy+round(y2*scale)),(0,190,255),2)
        padx=max(3,round((x2-x1)*.2));pady=max(3,round((y2-y1)*.1))
        cx,cy=max(0,x1-padx),max(0,y1-pady)
        crop=frame[cy:min(h,y2+pady),cx:min(w,x2+padx)]
        scale=min(340/crop.shape[1],490/crop.shape[0],8)
        cw,ch=round(crop.shape[1]*scale),round(crop.shape[0]*scale)
        ox,oy=672+(340-cw)//2,55+(500-ch)//2
        card[oy:oy+ch,ox:ox+cw]=cv2.resize(crop,(cw,ch),interpolation=cv2.INTER_CUBIC)
        cv2.rectangle(card,(ox+round((x1-cx)*scale),oy+round((y1-cy)*scale)),(ox+round((x2-cx)*scale),oy+round((y2-cy)*scale)),(0,190,255),2)
        cv2.putText(card,f"Source {w}x{h} | Target {row['pixels'][0]}x{row['pixels'][1]} px | plain resize",(16,582),cv2.FONT_HERSHEY_SIMPLEX,.48,(65,75,90),1)
        name=f"view-r{revision}-t{ident}-f{round(row['t']*fps) if fps else 0}-{key}.jpg"
        ok,encoded=cv2.imencode('.jpg',card,[cv2.IMWRITE_JPEG_QUALITY,91])
        if not ok:raise ValueError('encode')
        content=encoded.tobytes();temp=directory/(str(uuid4())+'.tmp');temp.write_bytes(content);temp.replace(directory/name)
        row.pop('score');frames.append({**row,'image':name,'sha256':hashlib.sha256(content).hexdigest()})
    manifest={'version':2,'target':ident,'revision':revision,'cache_sha256':request['cache_sha256'],'frames':frames,'purposes':purposes,'consistency':consistency}
    output=directory/request['manifest'];temp=directory/(str(uuid4())+'.tmp')
    temp.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8');temp.replace(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True)
    make_cards(parser.parse_args().request)
