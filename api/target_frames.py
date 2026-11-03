"""Authorized local frame extraction. Only bounded image bytes enter the model request."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from api.catalog import ROOT
from api.review_service import vision_environment


def prepare_target_frames(service,scene_id,owner,ident,aspects=None):
    from api.uploads import UploadError
    if not isinstance(ident,str) or not ident.isdecimal():raise ValueError('请指定当前素材的编号。')
    upload_id=scene_id.removeprefix('upload-')
    aspects=aspects or []
    if not isinstance(aspects,list) or any(a not in ('body','height','action','clothing','appearance','gender','carrying') for a in aspects):raise ValueError('不支持的取图方面。')
    purposes=sorted(set(('body' if a in ('body','height') else 'motion' if a=='action' else 'detail') for a in aspects))
    with service._lock:
        job=service._authorized(upload_id,owner)
        data=deepcopy(job['result']);directory=service._path(upload_id)
        target=next((t for t in (data or {}).get('targets',[]) if t['id']==ident),None)
        if job['status']!='complete' or not target:raise ValueError('当前素材没有这个编号。')
        revision=data.get('revision',1);cache_sha=data.get('cache_sha256')
        if not cache_sha or not target.get('samples'):raise ValueError('这份旧记录缺少原始位置或素材副本，未能取出目标画面。')
        key=hashlib.sha256(f'v2:{cache_sha}:{revision}:{ident}:{purposes}'.encode()).hexdigest()[:12]
        manifest_name=f'visual-r{revision}-t{ident}-{key}.json';manifest_path=directory/manifest_name
    if not manifest_path.is_file():
        request_path=directory/(f'inspect-{uuid4()}.json')
        request_path.write_text(json.dumps({'target':ident,'revision':revision,'key':key,'cache_sha256':cache_sha,'manifest':manifest_name,'purposes':purposes}),encoding='utf8')
        try:
            process=subprocess.run([str(service.python),str(ROOT/'vision/target_frames.py'),'--request',str(request_path)],
                cwd=ROOT,env=vision_environment(),capture_output=True,timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            if process.returncode:raise ValueError('目标画面暂时未能读取，请稍后重试。')
        except subprocess.TimeoutExpired as e:raise ValueError('挑选目标画面超时，请稍后重试。') from e
        finally:request_path.unlink(missing_ok=True)
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    if manifest.get('target')!=ident or manifest.get('revision')!=revision or manifest.get('cache_sha256')!=cache_sha:raise ValueError('画面版本不匹配。')
    if manifest.get('purposes',[])!=purposes:raise ValueError('画面用途不匹配。')
    frames=manifest.get('frames',[])
    if not 1<=len(frames)<=3:raise ValueError('缺少可用的目标画面。')
    images=[];metadata=[];evidence=[]
    for frame in frames:
        sample=next((s for s in target['samples'] if s['t']==frame.get('t') and s['bbox']==frame.get('bbox')),None)
        name=frame.get('image','')
        if not sample or Path(name).name!=name or not name.startswith(f'view-r{revision}-t{ident}-') or not name.endswith('.jpg'):raise ValueError('画面不属于当前编号。')
        content=(directory/name).read_bytes()
        if not 0<len(content)<=700000 or hashlib.sha256(content).hexdigest()!=frame.get('sha256'):raise ValueError('目标画面校验失败。')
        evidence_id=f'upload-{upload_id}-r{revision}-t{ident}-v{round(frame["t"]*data["sample_fps"]) if data["sample_fps"] else 0}-{key}'
        metadata.append({k:v for k,v in {**frame,'evidence_id':evidence_id}.items() if k!='image'})
        evidence.append({'id':evidence_id,'t':frame['t'],'image':name,'track_id':ident,'target_ids':[ident],
                         'description':f'编号 #{ident} 的实际画面与局部放大'})
        images.append('data:image/jpeg;base64,'+base64.b64encode(content).decode('ascii'))
    with service._lock:
        current=service._authorized(upload_id,owner)
        if current['result'].get('revision',1)!=revision:raise ValueError('识别结果已更新，请重试以查看当前画面。')
        existing={e['id'] for e in current['result']['evidence']}
        current['result']['evidence'].extend(e for e in evidence if e['id'] not in existing)
        service._write(current)
        return {'scene':service._result(current),'frames':metadata,'images':images,'consistency':manifest.get('consistency',{})}
