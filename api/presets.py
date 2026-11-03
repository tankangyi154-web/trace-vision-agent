"""Public, precomputed examples. Opening a demo never starts inference or a model call."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import time
from api.catalog import ROOT

ORDER=('daylight','lowlight','occlusion')


def load_preset(ident,root=None):
    root=Path(root or ROOT)
    if ident not in ORDER:raise KeyError(ident)
    try:data=json.loads((root/'data/presets'/f'{ident}.json').read_text(encoding='utf8'))
    except (OSError,ValueError) as error:raise KeyError(ident) from error
    if data.get('schema')!=1 or data.get('id')!=ident or data.get('result',{}).get('data_kind')!='uploaded_media':raise ValueError('Invalid prepared example')
    return data


def public_result(data):
    result=deepcopy(data['result'])
    def url(name):return f"/media/presets/{data['id']}/{name}?v={data['version']}"
    result['media_url']=url(result.pop('media'));result['poster_url']=url(result.pop('poster'))
    result['annotation_source_url']=url(result.pop('source_media'))
    for row in result['evidence']+result['highlights']:row['image_url']=url(row.pop('image'))
    return result


def list_presets(root=None):
    rows=[]
    for ident in ORDER:
        try:data=load_preset(ident,root)
        except KeyError:continue
        result=data['result']
        rows.append({**{k:data[k] for k in ('id','title','focus','subtitle','version','duration')},
            'poster_url':f"/media/presets/{ident}/{result['poster']}?v={data['version']}",
            'class_names':[row['name'] for row in result['counts']],
            'max_simultaneous':result['max_simultaneous']})
    return rows


def guide_answers(data):
    """Facts computed from saved observations; explicitly not recorded LLM output."""
    from api.media_profile import track_profile
    result=public_result(data);evidence=result['evidence'];counts=result['counts']
    def proofs(ids):return [{**row,'track_id':row.get('track_id','')} for row in evidence if row['id'] in ids][:3]
    peak=max(result['frame_counts'],key=lambda row:sum(row['counts'].values()))
    peak_evidence=min(evidence,key=lambda row:abs(row['t']-peak['t']))
    rows=[{'id':'inventory','question':'画面里识别到了什么？',
        'answer':f"共识别到{len(counts)}种物体："+'、'.join(row['name'] for row in counts)+'。可点击画面下方的类别筛选，单独查看。',
        'citations':[peak_evidence]},
        {'id':'peak','question':'哪一刻识别到的物体最多？',
         'answer':f"在{peak['t']:g}秒的采样画面中，同时标记了{sum(peak['counts'].values())}个物体。点击截图回到这一刻；数量来自检测结果，可能有遗漏或误检。",
         'citations':[peak_evidence]}]
    target=next((t for t in result['targets'] if t['id']==data.get('featured_target_id')),None)
    if target:
        profile=track_profile(result,target)
        text=f"{target['name']}首次识别于{target['first_seen']:g}秒，最后一次识别于{target['last_seen']:g}秒。"
        text+=' '+profile['trajectory']['text']
        gaps=(profile['visibility'].get('value') or {}).get('gap_count')
        if gaps:text+=f' 中途有{gaps}段没有识别到，原因需要结合画面核对。'
        rows.append({'id':'target','question':f"跟着{target['name']}回看经过",'target_id':target['id'],
            'answer':text+' 首次和末次识别不等于真实进入或离开；中间没有识别到时，需结合前后画面核对。',
            'citations':proofs(target['evidence_ids'])})
    if data['id']=='lowlight':
        rows.append({'id':'limits','question':'夜间结果应该怎么看？',
            'answer':'这段原片包含暗部、车灯和前景遮挡。识别框代表程序找到的物体；没有框的位置也可能存在未检出的物体。可切换“查看原片”，逐帧核对，不把未检出解释成不存在。',
            'citations':[peak_evidence]})
    if data.get('gap_review'):
        gap=data['gap_review']
        rows.append({'id':'gap','question':'交错遮挡前后怎么核对这个人？','target_id':gap['target_id'],
            'answer':f"这两张画面分别对应{gap['after']:g}秒和{gap['before']:g}秒。中间有{gap['missing_sample_seconds']:g}秒的采样画面没有匹配到这个编号。可对照前后的衣着与位置核对；中间的移动过程仍不能确认。",
            'citations':proofs(gap['evidence_ids'])})
    return rows


def get_preset(ident,root=None):
    data=load_preset(ident,root)
    return {**{k:data[k] for k in ('id','title','focus','subtitle','version','duration','source','featured_target_id')},
        'analysis_mode':'precomputed','external_model_calls_on_open':0,'result':public_result(data),'guides':guide_answers(data)}


def open_private_copy(service,ident,owner,root=None):
    """A separate owner-scoped working copy enables the existing upload Agent safely."""
    from api.uploads import UploadError
    root=Path(root or ROOT);data=load_preset(ident,root)
    with service._lock:
        expected_owner=hashlib.sha256(owner.encode()).hexdigest()
        for path in service.directory.glob('*/job.json'):
            try:job=service._read(path.parent.name)
            except UploadError:continue
            if job.get('owner')==expected_owner and job.get('preset_id')==ident and job.get('preset_version')==data['version'] and job['status']=='complete':return service._public(job)
        assets=root/'web/public/media/presets'/ident
        for name,metadata in data['assets'].items():
            if Path(name).name!=name or Path(name).suffix not in ('.jpg','.webm','.mp4','.png'):raise UploadError('processing')
            source=assets/name
            try:
                with source.open('rb') as handle:sha=hashlib.file_digest(handle,'sha256').hexdigest()
                if sha!=metadata['sha256'] or source.stat().st_size!=metadata['bytes']:raise UploadError('processing')
            except OSError as error:raise UploadError('processing') from error
        raw=data['result'];job=service.reserve(owner,data['title']+'.mp4',data['assets'][raw['source_media']]['bytes'],raw['classes'][:3])
        directory=service._path(job['id'])
        try:
            for name in data['assets']:shutil.copyfile(assets/name,directory/name)
            source_id=raw['id'];scene_id=job['scene_id']
            def rebase(value):
                if isinstance(value,str):return value.replace(source_id,scene_id)
                if isinstance(value,list):return [rebase(v) for v in value]
                if isinstance(value,dict):return {k:rebase(v) for k,v in value.items()}
                return value
            result=rebase(raw)
            serialized=json.dumps(result,ensure_ascii=False)
            (directory/f"result-r{result['revision']}.json").write_text(serialized,encoding='utf8')
            (directory/'result.json').write_text(serialized,encoding='utf8')
            from vision.source_cache import write_source_cache
            write_source_cache(directory,{**{k:result[k] for k in ('kind','cache_file','source_sha256','duration','sample_fps','width','height','processed_frames','source_width','source_height')}})
            service._update(job['id'],status='complete',stage='示例已载入，无需重新识别',phase='complete',processed=result['processed_frames'],total=result['processed_frames'],
                classes=result['classes'],result=result,source_sha256=result['source_sha256'],preset_id=ident,preset_version=data['version'],expires_at=None,finished_at=time.time())
            return service.get(job['id'],owner)
        except BaseException:
            service.delete(job['id'],owner)
            raise
