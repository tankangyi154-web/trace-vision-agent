"""Local-only bounded vision jobs. Python API never imports Torch or YOLO."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import UUID,uuid4
from api.catalog import ROOT,get_scene
from api.investigation import CASE_ID,SOURCE_SHA,FRAME_RANGE,baseline_facts,merge_review,review_facts,scene_version

STAGES={'validating_source':'校验原视频与模型版本','loading_model':'加载本地YOLO11n（CPU）',
        'reviewing_frames':'实际复检疑点窗口原帧','writing_result':'保存真实检测与证据','complete':'核验源帧与检测记录'}


class ReviewError(Exception): pass


def vision_environment():
    # Vision has no need for any application/API/account credentials. A whitelist
    # also excludes unknown future secrets and proxy authorization variables.
    names=('SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS')
    env={name:os.environ[name] for name in names if name in os.environ}
    temp=ROOT/'work/review-tmp';temp.mkdir(parents=True,exist_ok=True)
    env.update(TEMP=str(temp),TMP=str(temp),PYTHONIOENCODING='utf-8',PYTHONUTF8='1',
               PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',YOLO_OFFLINE='true',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    return env


class ReviewService:
    def __init__(self,production=False,directory=None):
        self.production=production
        self.directory=Path(directory or ROOT/'work/reviews')
        self.python=ROOT/'work/vision-env'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
        self._lock=threading.RLock()
        self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='local-vision')
        self._active=None

    @property
    def reason(self):
        if self.production: return '此复核策略仅在本地CPU运行，线上不加载视觉模型。'
        if not self.python.is_file() or not (ROOT/'vision/weights/yolo11n.pt').is_file():
            return '尚未准备本项目的本地视觉环境或固定模型权重。'
        return None

    def _path(self,rid):
        try: canonical=str(UUID(str(rid)))
        except ValueError as e: raise ReviewError('not_found') from e
        return self.directory/canonical

    def _resolve(self,rid):
        canonical=str(UUID(str(rid)))
        path=self.directory/'.bindings'/f'{canonical}.json'
        if not path.is_file(): return canonical
        return str(UUID(json.loads(path.read_text(encoding='utf-8'))['review_id']))

    def _bind(self,requested,actual):
        if requested==actual: return
        directory=self.directory/'.bindings'; directory.mkdir(parents=True,exist_ok=True)
        path=directory/f'{str(UUID(requested))}.json'
        if path.is_file(): return
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps({'review_id':str(UUID(actual)),'case_id':CASE_ID}),encoding='utf-8')
        temp.replace(path)

    def _read(self,rid):
        path=self._path(rid)/'job.json'
        if not path.is_file(): raise ReviewError('not_found')
        return json.loads(path.read_text(encoding='utf-8'))

    def _update(self,rid,changes):
        with self._lock:
            obj=self._read(rid)
            if obj['status'] in ('complete','failed'): return obj
            obj.update(changes); obj['updated_at']=time.time()
            path=self._path(rid)/'job.json'; temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8'); temporary.replace(path)
            return obj

    def start(self,rid):
        if self.reason: raise ReviewError('review_unavailable')
        rid=str(UUID(str(rid)))
        with self._lock:
            resolved=self._resolve(rid)
            if resolved!=rid: return self.get(resolved)
            if (self._path(rid)/'job.json').is_file(): return self.get(rid)
            if self._active:
                active=self.get(self._active)
                if active['status'] in ('queued','running'):
                    self._bind(rid,active['review_id'])
                    return active
            # Recover a worker/result from a restarted API without launching duplicates.
            if self.directory.exists():
                for p in sorted(self.directory.glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
                    existing=self.get(p.parent.name)
                    if existing['status'] in ('queued','running'):
                        self._active=p.parent.name
                        self._bind(rid,existing['review_id'])
                        return existing
            directory=self._path(rid); directory.mkdir(parents=True,exist_ok=True)
            now=datetime.now(timezone.utc).isoformat()
            obj={'review_id':rid,'case_id':CASE_ID,'status':'queued','stage':'等待本地视觉工作进程',
                 'completed_frames':0,'total_frames':7,'created_at':now,'finished_at':None,
                 'updated_at':time.time(),'result':None,'error':None}
            (directory/'job.json').write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
            self._active=rid
            self._pool.submit(self._run,rid)
            return self.get(rid)

    def _run(self,rid):
        directory=self._path(rid)
        process=None
        timer=None
        try:
            self._update(rid,{'status':'running','stage':'启动固定7帧视觉复核'})
            with (directory/'worker.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen([str(self.python),str(ROOT/'vision/review_gap.py'),'--output',str(directory.resolve())],
                    cwd=ROOT,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',errors='replace',
                    env=vision_environment(),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                timer=threading.Timer(45,lambda:process.kill() if process.poll() is None else None); timer.daemon=True; timer.start()
                for line in process.stdout:
                    try: stage=json.loads(line)
                    except ValueError: continue
                    if stage.get('stage') in STAGES:
                        self._update(rid,{'status':'running','stage':STAGES[stage['stage']],
                                           'completed_frames':min(7,max(0,int(stage.get('completed_frames',0))))})
                if process.wait()!=0: raise ReviewError('worker_failed')
                timer.cancel()
                self._update(rid,{'stage':'逐项核验源帧、坐标、关联门控与哈希'})
                check=subprocess.run([str(self.python),str(ROOT/'vision/validate_review.py'),'--output',str(directory.resolve())],
                    cwd=ROOT,stdout=log,stderr=log,timeout=15,
                    env=vision_environment(),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                if check.returncode: raise ReviewError('evidence_validation_failed')
            self._complete(rid)
        except Exception:
            self._update(rid,{'status':'failed','stage':'本地复核未完成','finished_at':datetime.now(timezone.utc).isoformat(),
                'error':{'code':'review_failed','message':'本地复核或证据校验失败；原始分析保留。未生成可采纳的新观测。'}})
        finally:
            if timer: timer.cancel()
            if process is not None and process.poll() is None: process.kill()

    def _complete(self,rid):
        directory=self._path(rid)
        result=json.loads((directory/'result.json').read_text(encoding='utf-8'))
        model=json.loads((ROOT/'vision/model.lock.json').read_text(encoding='utf-8'))
        if result['source_sha256']!=SOURCE_SHA or result['scene_sha256']!=scene_version() or result['model_sha256']!=model['sha256']:
            raise ReviewError('evidence_version_mismatch')
        if tuple(f['frame'] for f in result['frames'])!=FRAME_RANGE or len(result['observations'])>7:
            raise ReviewError('invalid_frame_budget')
        config=result['config']
        for name,value in {'imgsz':960,'confidence':.25,'iou':.5,'classes':[8],'device':'cpu','max_frames':7,'association_iou':.2,'ambiguity_margin':.1}.items():
            if config.get(name)!=value: raise ReviewError('strategy_mismatch')
        hashes={}
        for frame in result['frames']:
            if frame['t']!=frame['frame']/10: raise ReviewError('timestamp_mismatch')
            for key in ('original_image','crop_image','overlay_image'):
                filename=frame[key]
                if Path(filename).name!=filename or not filename.endswith('.jpg'): raise ReviewError('invalid_artifact')
                path=directory/filename
                hashes[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
                frame[key]=f'/review-media/{rid}/{filename}'
        result['artifact_hashes']=hashes
        result['worker_sha256']=hashlib.sha256((ROOT/'vision/review_gap.py').read_bytes()).hexdigest()
        merged=merge_review(get_scene('harbor'),result,rid)
        # Validate merge before publishing a terminal successful job.
        review_facts(merged,result,5)
        self._update(rid,{'status':'complete','stage':'复核完成，原帧与检测记录已核验','completed_frames':7,
                          'result':result,'finished_at':datetime.now(timezone.utc).isoformat(),'error':None})

    def get(self,rid,threshold=5):
        with self._lock:
            rid=self._resolve(rid)
            obj=self._read(rid)
            if obj['status'] in ('queued','running') and time.time()-obj['updated_at']>70:
                # A stale job is unknown, never silently replaced by another inference.
                obj=self._update(rid,{'status':'failed','stage':'原复核执行状态未知','finished_at':datetime.now(timezone.utc).isoformat(),
                    'error':{'code':'review_unknown','message':'原复核未返回最终状态，请检查本地工作进程；不会自动另起一次。'}})
            before=baseline_facts(get_scene('harbor'),threshold)
            obj['baseline']=before; obj['after']=None; obj['verification']=None
            if obj['status']=='complete':
                result=obj['result']
                if result['scene_sha256']!=scene_version(): raise ReviewError('evidence_version_mismatch')
                obj['after']=review_facts(merge_review(get_scene('harbor'),result,str(rid)),result,threshold)
                obj['verification']={'status':'case_evidence_checked','checks':[
                    {'name':'原视频/模型/场景版本绑定','passed':True,'detail':'SHA256匹配固定案例'},
                    {'name':'7帧来源、裁剪与检测门控','passed':True,'detail':'源帧重解码比对与几何门控已复算'},
                    {'name':'缺口全部获得可关联候选','passed':not obj['after']['unknown_frames'],
                     'detail':f"接受{len(result['observations'])}/7帧；未解帧不以合成数据补入"}],
                    'limitations':result['limitations']}
            return obj

    def latest(self):
        if not self.directory.exists(): return None
        for p in sorted(self.directory.glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            try:
                if self.get(p.parent.name)['status']=='complete': return p.parent.name
            except (ReviewError,ValueError,KeyError): continue
        return None

    def wait(self,rid=None,on_stage=None):
        obj=self.get(rid) if rid else self.start(str(uuid4()))
        deadline=time.monotonic()+65
        while obj['status'] in ('queued','running'):
            if on_stage: on_stage({'stage':'视觉工具：'+obj['stage']})
            if time.monotonic()>deadline: raise ReviewError('review_timeout')
            time.sleep(.3)
            obj=self.get(obj['review_id'])
        if obj['status']!='complete': raise ReviewError('review_failed')
        return obj
