"""Bounded local inference for one private upload. No URLs or application credentials."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from vision.annotation import annotate
from vision.media_tracking import create_trackers,tracked_detections
from vision.media_detection import MediaDetector,normalization_bounds,POLICY_PATH
MEDIA_LIMITS=json.loads((ROOT/'data/media-limits.json').read_text(encoding='utf8'))
IMAGE_MAX_BYTES=MEDIA_LIMITS['image_max_mb']*1024*1024
VIDEO_MAX_BYTES=MEDIA_LIMITS['video_max_mb']*1024*1024
VIDEO_MAX_SECONDS=MEDIA_LIMITS['video_max_seconds']
SAMPLE_FPS=MEDIA_LIMITS['sample_fps']
MAX_VIDEO_FRAMES=VIDEO_MAX_SECONDS*SAMPLE_FPS
WORKER_TIMEOUT_SECONDS=MEDIA_LIMITS['worker_timeout_seconds']
MAX_INFLIGHT=MEDIA_LIMITS['max_inflight']
MEDIA_WAIT_SECONDS=WORKER_TIMEOUT_SECONDS*MAX_INFLIGHT+30
NAMES=dict(zip(
    'person bicycle car motorcycle airplane bus train truck boat traffic_light fire_hydrant stop_sign parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella handbag tie suitcase frisbee skis snowboard sports_ball kite baseball_bat baseball_glove skateboard surfboard tennis_racket bottle wine_glass cup fork knife spoon bowl banana apple sandwich orange broccoli carrot hot_dog pizza donut cake chair couch potted_plant bed dining_table toilet tv laptop mouse remote keyboard cell_phone microwave oven toaster sink refrigerator book clock vase scissors teddy_bear hair_drier toothbrush'.split(),
    '人 自行车 汽车 摩托车 飞机 公交车 火车 卡车 船 交通灯 消防栓 停车标志 停车计时器 长椅 鸟 猫 狗 马 羊 牛 大象 熊 斑马 长颈鹿 背包 雨伞 手提包 领带 行李箱 飞盘 滑雪板 单板滑雪板 球 风筝 棒球棒 棒球手套 滑板 冲浪板 网球拍 瓶子 酒杯 杯子 叉子 刀 勺子 碗 香蕉 苹果 三明治 橙子 西兰花 胡萝卜 热狗 披萨 甜甜圈 蛋糕 椅子 沙发 盆栽 床 餐桌 马桶 电视 笔记本电脑 鼠标 遥控器 键盘 手机 微波炉 烤箱 烤面包机 水槽 冰箱 书 时钟 花瓶 剪刀 泰迪熊 吹风机 牙刷'.split()))


def label_name(label): return NAMES.get(label.replace(' ','_'),label)
CLASS_ALIASES={
    'person':['行人','人类','people'], 'bicycle':['单车','脚踏车','bike'],
    'car':['车','轿车','小汽车'], 'motorcycle':['摩托','motorbike'],
    'airplane':['aeroplane'], 'bus':['大巴','巴士','公交'], 'truck':['货车'],
    'boat':['船舶','轮船'], 'traffic_light':['红绿灯','信号灯'],
    'couch':['沙发椅','sofa'], 'potted_plant':['盆栽植物'], 'dining_table':['饭桌'],
    'tv':['电视机','television'], 'laptop':['笔记本','laptop computer'],
    'cell_phone':['移动电话','mobile phone','smartphone'], 'remote':['遥控'],
    'cup':['水杯','茶杯'], 'wine_glass':['葡萄酒杯'], 'refrigerator':['电冰箱','fridge'],
    'hair_drier':['电吹风','吹风筒','hair dryer'], 'sports_ball':['运动球'],
}


def class_choices():return [{'id':i,'label':en.replace('_',' '),'name':cn,'aliases':CLASS_ALIASES.get(en,[])} for i,(en,cn) in enumerate(NAMES.items())]


def validate_classes(value):
    if not isinstance(value,list) or not 1<=len(value)<=3 or any(type(i) is not int or not 0<=i<len(NAMES) for i in value) or len(set(value))!=len(value):
        raise ValueError('targets')
    return list(value)


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
def stage(name,**values): print(json.dumps({'stage':name,**values}),flush=True)


def validated_metadata(width,height,fps=0,frames=0,kind='image'):
    if width<8 or height<8 or width*height>20_000_000 or max(width,height)>8192:
        raise ValueError('dimensions')
    if kind=='video':
        if not math.isfinite(fps) or not .5<=fps<=240 or frames<=0: raise ValueError('decode')
        if frames/fps>VIDEO_MAX_SECONDS+.05: raise ValueError('duration')
    return frames/fps if kind=='video' else 0


def infer(directory,classes=None,base_revision=0,scope=None):
    classes=validate_classes(classes)
    previous=json.loads((directory/f'result-r{base_revision}.json').read_text(encoding='utf8')) if base_revision else None
    if previous and (previous.get('revision')!=base_revision or set(classes).intersection(previous['classes'])):raise ValueError('targets')
    all_classes=list(dict.fromkeys([*(previous['classes'] if previous else []),*classes]))
    chosen=[class_choices()[i] for i in all_classes];revision=base_revision+1
    # Keep third-party caches inside this expiring job; the child has no user profile or application secrets.
    for name,subdir in [('YOLO_CONFIG_DIR','yolo'),('MPLCONFIGDIR','mpl')]:
        path=directory/'runtime'/subdir;path.mkdir(parents=True,exist_ok=True);os.environ[name]=str(path)
    os.environ['YOLO_OFFLINE']='true'
    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']='protocol_whitelist;file,pipe'
    import cv2
    import numpy as np
    import torch
    from PIL import Image,ImageDraw,ImageFont
    from ultralytics import YOLO
    import yaml
    started=time.perf_counter()
    from vision.media_scope import validate_scope,resolve_scope
    requested_scope=validate_scope(scope)
    analysis_scope=previous.get('analysis_scope') if previous else None
    timings={}
    cached=None
    if not previous and not list(directory.glob('source.*')):
        from vision.source_cache import read_source_cache
        cached=read_source_cache(directory)
    if previous:
        kind=previous['kind'];cache_file='analysis-source.png' if kind=='image' else 'analysis-source.mp4'
        if previous.get('cache_file')!=cache_file:raise ValueError('decode')
        source=directory/cache_file
        if digest(source)!=previous['cache_sha256']:raise ValueError('decode')
        source_sha=previous['source_sha256']
    elif cached:
        kind=cached['kind'];source=directory/cached['cache_file'];source_sha=cached['source_sha256']
        analysis_scope=cached.get('analysis_scope')
    else:
        sources=list(directory.glob('source.*'))
        if len(sources)!=1: raise ValueError('decode')
        source=sources[0];source_sha=digest(source)
        kind='image' if source.suffix.lower() in ('.jpg','.jpeg','.png','.webp') else 'video'
    lock=json.loads((ROOT/'vision/upload-model.lock.json').read_text(encoding='utf8'))
    model_path=ROOT/'vision/weights'/lock['model']
    if digest(model_path)!=lock['sha256']: raise ValueError('environment')
    ffmpeg=ROOT/'work/bin/ffmpeg.exe'
    if not ffmpeg.is_file():
        found=shutil.which('ffmpeg')
        if not found: raise ValueError('environment')
        ffmpeg=Path(found)
    def ff(args):
        p=subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-y',*args],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=MEDIA_LIMITS['ffmpeg_timeout_seconds'],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        if p.returncode: raise ValueError('decode')
    stage('checking')
    duration=0;sample_fps=0;cap=None;still=None
    if previous or cached:
        metadata=previous or cached
        duration=metadata['duration'];sample_fps=metadata['sample_fps'];width,height=metadata['width'],metadata['height'];total=metadata['processed_frames']
        source_width=metadata.get('source_width',width);source_height=metadata.get('source_height',height)
        if kind=='image':
            still=cv2.imread(str(source))
            if still is None or still.shape[:2]!=(height,width):raise ValueError('decode')
        else:
            cap=cv2.VideoCapture(str(source),cv2.CAP_FFMPEG)
            if not cap.isOpened() or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))!=total:raise ValueError('decode')
    elif kind=='image':
        if requested_scope is not None:raise ValueError('segment')
        raw=source.read_bytes()
        if not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG\r\n\x1a\n') or (raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')):
            raise ValueError('decode')
        with Image.open(io.BytesIO(raw)) as header: validated_metadata(*header.size)
        still=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
        if still is None: raise ValueError('decode')
        h,w=still.shape[:2];validated_metadata(w,h);source_width,source_height=w,h
        factor=min(1,1280/w,960/h)
        if factor<1: still=cv2.resize(still,(max(8,int(w*factor)),max(8,int(h*factor))))
        height,width=still.shape[:2];total=1
    else:
        with source.open('rb') as header_file:prefix=header_file.read(16)
        if source.suffix.lower()=='.webm':
            if not prefix.startswith(b'\x1aE\xdf\xa3'):raise ValueError('decode')
        elif prefix[4:8] not in (b'ftyp',b'moov',b'mdat',b'wide',b'free',b'skip'):
            raise ValueError('decode')
        cap=cv2.VideoCapture(str(source),cv2.CAP_FFMPEG)
        if not cap.isOpened(): raise ValueError('decode')
        w,h=int(cap.get(3)),int(cap.get(4));fps=cap.get(cv2.CAP_PROP_FPS);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.release()
        source_width,source_height=w,h
        duration=validated_metadata(w,h,fps,n,kind)
        analysis_scope=resolve_scope(requested_scope,duration)
        duration=analysis_scope['end_seconds']-analysis_scope['start_seconds']
        max_width,max_height=normalization_bounds(w,h,duration)
        # Normalize locally, strip audio/metadata; protocols cannot load remote media.
        ff(['-protocol_whitelist','file,pipe','-ss',str(analysis_scope['start_seconds']),'-i',str(source),'-t',str(duration),'-map','0:v:0','-an','-map_metadata','-1',
            '-vf',f"scale=w='min({max_width},iw)':h='min({max_height},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps={SAMPLE_FPS}",
            '-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p',str(directory/'analysis-source.mp4')])
        cap=cv2.VideoCapture(str(directory/'analysis-source.mp4'))
        total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));width,height=int(cap.get(3)),int(cap.get(4));sample_fps=SAMPLE_FPS
        if not 1<=total<=MAX_VIDEO_FRAMES: raise ValueError('duration')
    cache_file='analysis-source.png' if kind=='image' else 'analysis-source.mp4'
    if not previous and kind=='image' and not cv2.imwrite(str(directory/cache_file),still):raise ValueError('environment')
    if not previous and not cached:
        from vision.source_cache import write_source_cache
        write_source_cache(directory,{'kind':kind,'cache_file':cache_file,'source_sha256':source_sha,
            'duration':duration,'sample_fps':sample_fps,'width':width,'height':height,'processed_frames':total,
            'source_width':source_width,'source_height':source_height,'analysis_scope':analysis_scope})
    timings['prepare_seconds']=round(time.perf_counter()-started,3)
    phase_started=time.perf_counter()
    from vision.cpu_calibration import cpu_threads
    torch.set_num_threads(cpu_threads())
    stage('loading')
    from vision.device import inference_device
    device=inference_device()
    stage('loading',device=device,total=total,processed=0)
    cpu_models=None
    if device=='cpu':
        from vision.onnx_cpu import verified_models,OnnxDetector
        cpu_models=verified_models()
    with contextlib.redirect_stdout(sys.stderr): model=OnnxDetector(cpu_models['detector_session']) if cpu_models else YOLO(str(model_path))
    tracking_policy_sha=digest(ROOT/'vision/upload-tracking.json')
    tracking_policy=json.loads((ROOT/'vision/upload-tracking.json').read_text(encoding='utf8'))
    detection_policy_sha=digest(POLICY_PATH)
    if previous and kind=='video' and previous.get('processing',{}).get('tracking_policy_sha256')!=tracking_policy_sha:raise ValueError('version')
    if previous and kind=='video' and previous.get('processing',{}).get('detection_policy_sha256')!=detection_policy_sha:raise ValueError('version')
    detector=MediaDetector(model,lock,classes,kind,total,SAMPLE_FPS,device=device)
    appearance=None
    if kind=='video' and 0 in classes:
        from vision.appearance import PersonAppearance
        appearance=PersonAppearance(device=device,session=cpu_models['appearance_session'] if cpu_models else None)
    trackers=create_trackers(classes,yaml.safe_load((ROOT/'vision/bytetrack.yaml').read_text(encoding='utf8')),appearance) if kind=='video' else None
    samples=directory/'samples';samples.mkdir(exist_ok=True)
    targets={t['id']:deepcopy(t) for t in previous['targets']} if previous else {}
    offset=max((int(i) for i in targets),default=0)
    old_boxes=[[] for _ in range(total)]
    if previous:
        for target in targets.values():
            for sample in target['samples']:
                index=round(sample['t']*sample_fps) if kind=='video' else 0
                if not 0<=index<total:raise ValueError('decode')
                old_boxes[index].append({'id':target['id'],'label':target['label'],'bbox':sample['bbox']})
    identity_map={};frames=[];max_counts=Counter();class_votes={}
    timings['load_seconds']=round(time.perf_counter()-phase_started,3)
    phase_started=time.perf_counter()
    try:
        for index in range(total):
            if cap:
                ok,frame=cap.read()
                if not ok: raise ValueError('decode')
            else: frame=still
            with contextlib.redirect_stdout(sys.stderr):
                result=detector(frame)
            detections=result.boxes;boxes=list(old_boxes[index]);t=round(index/sample_fps,3) if kind=='video' else 0
            ids=None
            if trackers is not None:
                # Draw current measured rectangles, not lagging Kalman boxes;
                # preserve indices across confidence subsets and class gates.
                detections,ids=tracked_detections(trackers,detections,frame)
            for j,(bbox,confidence,cls) in enumerate(zip(detections.xyxyn.tolist(),detections.conf.tolist(),detections.cls.tolist())):
                if classes and int(cls) not in classes:raise ValueError('processing')
                raw_id=ids[j] if ids is not None else j+1
                if raw_id not in identity_map: identity_map[raw_id]=str(offset+len(identity_map)+1)
                ident=identity_map[raw_id];label=model.names[int(cls)]
                box={'id':ident,'label':label,'bbox':[round(min(1,max(0,v)),6) for v in bbox],'confidence':round(confidence,4)}
                boxes.append(box)
                class_votes.setdefault(ident,Counter())[label]+=confidence
                if ident not in targets: targets[ident]={'id':ident,'name':f'{label_name(label)} #{ident}','label':label,'first_seen':t,'last_seen':t,'samples':[]}
                targets[ident]['last_seen']=t;targets[ident]['samples'].append({'t':t,'bbox':box['bbox'],'confidence':box['confidence']})
            image_name=f'r{revision}-evidence-{index:04d}.jpg'
            frames.append({'index':index,'t':t,'boxes':boxes,'image':image_name})
            stage('detecting',processed=index+1,total=total,detection_elapsed_seconds=round(time.perf_counter()-phase_started,3))
    finally:
        if cap:cap.release()
    timings['detect_track_seconds']=round(time.perf_counter()-phase_started,3)
    phase_started=time.perf_counter()
    # Use one confidence-weighted type for each local tracking record, so a
    # transient class flip cannot change colors/counts midway through playback.
    for ident,votes in class_votes.items():targets[ident]['label']=votes.most_common(1)[0][0]
    for target in targets.values():target['name']=f"{label_name(target['label'])} #{target['id']}"
    for frame in frames:
        for box in frame['boxes']:box['label']=targets[box['id']]['label']
        for label,count in Counter(b['label'] for b in frame['boxes']).items():max_counts[label]=max(max_counts[label],count)
    stage('rendering',processed=total,total=total)
    counts=Counter(x['label'] for x in targets.values())
    ranked=sorted(counts,key=lambda k:(-counts[k],k))
    selected={0}
    if frames: selected.add(max(frames,key=lambda f:len(f['boxes']))['index'])
    # Every target has its own first/last evidence within the bounded sample grid.
    for target in targets.values():
        selected.add(round(target['first_seen']*sample_fps) if kind=='video' else 0)
        selected.add(round(target['last_seen']*sample_fps) if kind=='video' else 0)
    selected=sorted(selected)
    # A separate render pass keeps exported labels crisp on low-resolution
    # footage without feeding a sharpened or synthetic image to the detector.
    cap=cv2.VideoCapture(str(directory/cache_file)) if kind=='video' else None
    writer=None;render_scale=max(1,min(960/width,960/height));render_width=round(width*render_scale);render_height=round(height*render_scale)
    if render_width%2:render_width+=1
    if render_height%2:render_height+=1
    try:
        if kind=='video':
            writer=cv2.VideoWriter(str(directory/'render.avi'),cv2.VideoWriter_fourcc(*'MJPG'),sample_fps,(render_width,render_height))
            if not writer.isOpened():raise ValueError('environment')
        for item in frames:
            if cap:
                ok,frame=cap.read()
                if not ok:raise ValueError('decode')
            else:frame=still
            canvas=annotate(frame,item['boxes'],label_name)
            if canvas.shape[1::-1]!=(render_width,render_height):canvas=cv2.resize(canvas,(render_width,render_height))
            if item['index'] in selected and not cv2.imwrite(str(samples/item['image']),canvas,[cv2.IMWRITE_JPEG_QUALITY,92]):raise ValueError('environment')
            if writer:writer.write(canvas)
    finally:
        if cap:cap.release()
        if writer:writer.release()
    evidence=[];upload_id=directory.name
    for i in selected:
        frame=frames[i];shutil.copyfile(samples/frame['image'],directory/frame['image'])
        evidence.append({'id':f'upload-{upload_id}-r{revision}-e{i}','t':frame['t'],'image':frame['image'],
            'track_id':frame['boxes'][0]['id'] if frame['boxes'] else '',
            'target_ids':[b['id'] for b in frame['boxes']],
            'description':f"画面中标记{len(frame['boxes'])}个目标"})
    for target in targets.values():
        own=[e['id'] for e in evidence if target['id'] in e['target_ids']]
        target['evidence_ids']=list(dict.fromkeys([own[0],own[-1]])) if own else []
        target['label_name']=label_name(target['label'])
    if kind=='video':
        ff(['-i',str(directory/'render.avi'),'-an','-map_metadata','-1','-c:v','libvpx-vp9','-deadline','realtime',
            '-cpu-used','8','-crf','32','-b:v','0','-pix_fmt','yuv420p',str(directory/f'r{revision}-annotated.webm')])
        media=f'r{revision}-annotated.webm'
    else:
        media=f'r{revision}-annotated.jpg';shutil.copyfile(directory/evidence[0]['image'],directory/media)
    timings['render_encode_seconds']=round(time.perf_counter()-phase_started,3)
    category_names=[label_name(k) for k in ranked]
    short='、'.join(category_names[:3])+('等' if len(category_names)>3 else '')
    max_objects=max((len(f['boxes']) for f in frames),default=0)
    if not counts:summary='没有识别到可标记的常见物体。可以换一张更清晰的图片，或让目标在画面中更明显。'
    elif kind=='image': summary=f"识别到{short}，共{sum(counts.values())}个标记目标。点击下方目标，可以在图片中找到它。"
    else:summary=f"这段{duration:.1f}秒的视频中识别到{short}，画面中最多同时出现{max_objects}个标记目标。可以回看关键画面，或继续问我。"
    if chosen:
        scope='、'.join(c['name'] for c in chosen)
        summary=f'已查找{scope}。'+(summary if counts else '没有检出所选物体。可以继续告诉我还想找什么。')
    highlights=[];seen_labels=set()
    peak=max(frames,key=lambda f:len(f['boxes']))
    if peak['boxes']:highlights.append(next(e for e in evidence if e['t']==peak['t']))
    for e in evidence:
        labels={b['label'] for b in frames[round(e['t']*sample_fps) if kind=='video' else 0]['boxes']}
        if labels-seen_labels and e not in highlights:highlights.append(e)
        seen_labels.update(labels)
        if len(highlights)>=4:break
    output={'id':f'upload-{upload_id}','data_kind':'uploaded_media','kind':kind,'duration':round(duration,3),
        'sample_fps':sample_fps,'width':width,'height':height,'media':media,'poster':evidence[0]['image'],'source_media':cache_file,
        'source_width':source_width,'source_height':source_height,'analysis_scope':analysis_scope,
        'quality':{'low_resolution':min(source_width,source_height)<480,'note':'原视频清晰度较低，远处或被遮挡的物体仍可能漏识别。' if min(source_width,source_height)<480 else ''},
        'processing':{'device':device,'inference_backend':'onnxruntime-cpu' if cpu_models else 'pytorch-'+('cuda' if device!='cpu' else 'cpu'),'timings':timings,'model':lock['model'],'imgsz':detector.options['imgsz'],'confidence':detector.options['conf'],'iou':detector.options['iou'],'max_det':detector.options['max_det'],'new_track_confidence':.25,'sample_fps':sample_fps,'class_aware_tracking':True,'type_stabilization':'confidence_weighted_track_vote',
            'detection_policy':'adaptive-density-v1','detection_policy_sha256':detection_policy_sha,'dense_detection':detector.dense,'dense_frames':detector.dense_frames,'extra_detection_passes':detector.extra_passes,
            'tracking_policy':tracking_policy['version'],'tracking_policy_sha256':tracking_policy_sha,
            'appearance_model_sha256':appearance.lock['sha256'] if appearance else previous.get('processing',{}).get('appearance_model_sha256') if previous else None,
            'tracking_diagnostics':getattr(trackers.get(0),'diagnostics',{}) if trackers else {}},
        'summary':summary,'source_sha256':source_sha,'model_sha256':lock['sha256'],
        'processed_frames':total,'max_simultaneous':max_objects,
        'counts':[{'label':k,'name':label_name(k),'count':counts[k],'max_simultaneous':max_counts[k]} for k in ranked],
        'frame_counts':[{'t':f['t'],'counts':dict(Counter(b['label'] for b in f['boxes']))} for f in frames],
        'targets':list(targets.values()),'evidence':(previous['evidence'] if previous else [])+evidence,'highlights':highlights,'labels':NAMES,
        'classes':all_classes,'class_labels':[c['label'] for c in chosen],'class_names':[c['name'] for c in chosen],
        'revision':revision,'added_classes':classes,'cache_file':cache_file,'cache_sha256':digest(directory/cache_file),
        'media_history':list(dict.fromkeys([*(previous.get('media_history',[]) if previous else []),*([previous['media']] if previous else [])])),
        'elapsed_ms':round((time.perf_counter()-started)*1000),
        'counting_method':'image_instances' if kind=='image' else 'tracking_records_not_unique_physical_objects'}
    from vision.pipeline import pipeline_fingerprint
    output['processing']['pipeline_fingerprint']=pipeline_fingerprint()
    serialized=json.dumps(output,ensure_ascii=False,separators=(',',':'))
    temp=directory/'result.tmp';temp.write_text(serialized,encoding='utf8');temp.replace(directory/f'result-r{revision}.json')
    (directory/'result.json').write_text(serialized,encoding='utf8')
    stage('complete',processed=total,total=total)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--classes',required=True);parser.add_argument('--base-revision',type=int,default=0);parser.add_argument('--scope',default='null');args=parser.parse_args()
    directory=args.directory.resolve();base=(ROOT/'work/uploads').resolve()
    if directory.parent!=base or str(UUID(directory.name))!=directory.name:raise ValueError('output')
    try:infer(directory,validate_classes(json.loads(args.classes)),args.base_revision,json.loads(args.scope))
    except Exception as e:
        code=str(e) if isinstance(e,ValueError) and str(e) in ('dimensions','duration','decode','environment','targets','version','segment') else 'processing'
        stage('error',code=code)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':sys.exit(main())
