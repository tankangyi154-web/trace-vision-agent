"""Private local records; incomplete jobs expire, completed analyses survive until deletion."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
from uuid import UUID,uuid4
from api.catalog import ROOT
from api.review_service import vision_environment
from api.runtime import vision_python
from vision.media_scope import validate_scope
from vision.pipeline import pipeline_fingerprint
from vision.analyze_media import (validate_classes,class_choices,digest,MEDIA_LIMITS,IMAGE_MAX_BYTES,VIDEO_MAX_BYTES,
    MAX_VIDEO_FRAMES,WORKER_TIMEOUT_SECONDS,MAX_INFLIGHT,MEDIA_WAIT_SECONDS)

IMAGE_EXTS={'.jpg','.jpeg','.png','.webp'}
VIDEO_EXTS={'.mp4','.mov','.webm'}
RETENTION=30*60
SAMPLE_SHORT_FRAMES=MEDIA_LIMITS['sample_fps']*30
STAGES={'checking':'正在读取你的文件','loading':'正在准备图像识别','detecting':'正在识别画面中的物体',
        'rendering':'正在生成标注画面和关键截图','complete':'正在整理分析结果'}
ERROR_MESSAGES={'duration':f"视频超过{MEDIA_LIMITS['video_max_seconds']//60}分钟，请截取后再试。",'dimensions':'图片或视频尺寸过大，请缩小到2000万像素以内。',
    'decode':'这个文件无法读取，请换用清晰的JPG、PNG、WebP图片，或MP4、MOV、WebM视频。',
    'environment':'本机分析服务暂时不可用，请稍后再试。','processing':'分析中断了，可以重试当前素材；不必先更换文件。',
    'timeout':f'分析达到{WORKER_TIMEOUT_SECONDS//60}分钟处理上限，尚未完成。可以直接重试当前素材。',
    'segment':'所选时间段无效或超出视频长度，请调整开始与结束时间。',
    'busy':'前面的文件还在处理中，请稍后再试。','not_found':'这份分析已删除或过期，请重新上传。',
    'disabled':'当前环境暂不支持本地文件分析。','size':f"图片请不超过{MEDIA_LIMITS['image_max_mb']}MB，视频请不超过{MEDIA_LIMITS['video_max_mb']}MB。",'format':'请上传JPG、PNG、WebP图片，或MP4、MOV、WebM短视频。',
    'targets':'请先选择1—3种要找的物体，不能重复。','source_expired':'这份记录的素材副本缺失，无法继续补查；已有结果仍可查看。',
    'version':'这份结果使用旧版跟踪，请重新上传后使用新版分析。'}


class UploadError(Exception):
    def __init__(self,code):self.code=code;super().__init__(ERROR_MESSAGES.get(code,ERROR_MESSAGES['processing']))


class ProcessTree:
    """Own the worker and its ffmpeg children. A Windows Job also closes on API death."""
    def __init__(self,process):
        self.process=process;self._lock=threading.Lock();self.handle=None
        if sys.platform=='win32':
            import ctypes
            from ctypes import wintypes as w
            class Basic(ctypes.Structure):
                _fields_=[('user',ctypes.c_int64),('job',ctypes.c_int64),('flags',w.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
            class Extended(ctypes.Structure):
                _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
            kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
            kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
            kernel.TerminateJobObject.argtypes=[w.HANDLE,w.UINT]
            kernel.CloseHandle.argtypes=[w.HANDLE]
            handle=kernel.CreateJobObjectW(None,None)
            info=Extended();info.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not handle or not kernel.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(handle,int(process._handle)):
                if handle:kernel.CloseHandle(handle)
                process.kill();process.wait()
                raise UploadError('environment')
            self.kernel=kernel;self.handle=handle

    def kill(self):
        with self._lock:
            if sys.platform=='win32':
                if self.handle:self.kernel.TerminateJobObject(self.handle,1)
            else:
                import signal
                try:os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:raise UploadError('processing')

    def close(self):
        with self._lock:
            if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


def pid_alive(pid):
    if not pid:return False
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes as w
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.CloseHandle.argtypes=[w.HANDLE]
        handle=k.OpenProcess(0x100000,False,pid)
        if not handle:return ctypes.get_last_error()==5 # Protect a process we cannot inspect.
        try:return k.WaitForSingleObject(handle,0)==0x102
        finally:k.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True


def validate_upload(filename,size):
    ext=Path(filename).suffix.lower()
    kind='image' if ext in IMAGE_EXTS else 'video' if ext in VIDEO_EXTS else None
    if not kind:raise UploadError('format')
    if not 0<size<=(IMAGE_MAX_BYTES if kind=='image' else VIDEO_MAX_BYTES):raise UploadError('size')
    return kind


class UploadService:
    def __init__(self,directory=None,enabled=True,on_remove=None):
        self.directory=Path(directory or ROOT/'work/uploads').resolve();self.enabled=enabled
        self.python=vision_python(ROOT)
        self._lock=threading.RLock();self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='media-upload')
        self._processes={};self._done={};self._supplements={};self._deleted=set();self._stopping=threading.Event();self.on_remove=on_remove

    def _path(self,ident):
        try:canonical=str(UUID(str(ident)))
        except ValueError as e:raise UploadError('not_found') from e
        path=(self.directory/canonical).resolve()
        if path.parent!=self.directory:raise UploadError('not_found')
        return path

    def _write(self,job):
        directory=self._path(job['id'])
        if not directory.is_dir():return
        temp=directory/'job.tmp';temp.write_text(json.dumps(job,ensure_ascii=False),encoding='utf8');temp.replace(directory/'job.json')

    def _read(self,ident):
        path=self._path(ident)/'job.json'
        try:job=json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError) as e:raise UploadError('not_found') from e
        # Completed local analyses are user records, retained until deletion.
        if job['status']=='complete' and job.get('result'):
            if job.get('expires_at') is not None:
                job['expires_at']=None;self._write(job)
        elif job['expires_at']<=time.time():
            pending=self._done.get(ident)
            if job['status'] in ('queued','running') and pending and not pending.is_set() and job.get('manager_pid')==os.getpid():
                job['expires_at']=time.time()+RETENTION;self._write(job)
            else:raise UploadError('not_found')
        return job

    def _update(self,ident,**values):
        with self._lock:
            if ident in self._deleted:return
            job=self._read(ident);job.update(values);self._write(job)

    def available(self):
        from api.runtime import inspect_runtime
        return self.enabled and self.python.is_file() and inspect_runtime(ROOT)['image_analysis']

    def reserve(self,owner,filename,size,classes=None,scope=None):
        if not self.enabled:raise UploadError('disabled')
        kind=validate_upload(filename,size)
        try:scope=validate_scope(scope,kind,MEDIA_LIMITS['video_max_seconds'])
        except ValueError as error:raise UploadError('segment') from error
        try:classes=validate_classes(classes)
        except ValueError as e:raise UploadError('targets') from e
        with self._lock:
            self.cleanup()
            active=0
            for path in self.directory.glob('*/job.json'):
                try:job=self._read(path.parent.name)
                except UploadError:continue
                if job['status'] in ('uploading','queued','running') or job.get('updating'):active+=1
            if active>=MAX_INFLIGHT:raise UploadError('busy')
            ident=str(uuid4());directory=self._path(ident);directory.mkdir(parents=True)
            job={'id':ident,'scene_id':'upload-'+ident,'owner':hashlib.sha256(owner.encode()).hexdigest(),
                'asset_token':secrets.token_urlsafe(24),'filename':Path(filename.replace('\\','/')).name[:120],
                'kind':kind,'classes':classes,'initial_classes':classes,'updating':False,'status':'uploading','stage':'正在接收文件','processed':0,'total':0,
                'requested_scope':scope,
                'created_at':time.time(),'expires_at':time.time()+RETENTION,'manager_pid':os.getpid(),'result':None,'error':None}
            self._write(job)
            return self._public(job)

    def _authorized(self,ident,owner):
        job=self._read(ident)
        if not secrets.compare_digest(job['owner'],hashlib.sha256(owner.encode()).hexdigest()):raise UploadError('not_found')
        return job

    def _result(self,job):
        result=deepcopy(job['result'])
        if not result:return None
        def url(name):return f"/api/uploads/{job['id']}/assets/{name}?token={job['asset_token']}"
        result['media_url']=url(result.pop('media'));result['poster_url']=url(result.pop('poster'))
        if result.get('source_media'):result['annotation_source_url']=url(result.pop('source_media'))
        for item in result['evidence']+result['highlights']:item['image_url']=url(item.pop('image'))
        return result

    def _public(self,job):
        return {**{k:job[k] for k in ('id','scene_id','filename','kind','status','stage','processed','total','created_at','expires_at','error')},
                'classes':job.get('classes',[]),'initial_classes':job.get('initial_classes',job.get('classes',[])[:3]),'updating':job.get('updating',False),
                'error_code':job.get('error_code'),'phase':job.get('phase'),
                'requested_scope':job.get('requested_scope'),'eta_seconds':job.get('eta_seconds') if job.get('phase')=='detecting' else None,
                'elapsed_seconds':max(0,round((job.get('finished_at') or time.time())-job['started_at'])) if job.get('started_at') else 0,
                'can_retry':job['status']=='failed' and (self._path(job['id'])/'source-cache.json').is_file(),
                'class_names':[class_choices()[i]['name'] for i in job.get('classes',[])],'result':self._result(job)}

    def get(self,ident,owner):
        with self._lock:return self._public(self._authorized(ident,owner))

    def records(self,owner):
        rows=[]
        with self._lock:
            if not self.enabled:return rows
            for record in self.directory.glob('*/job.json'):
                try:job=self._authorized(record.parent.name,owner)
                except UploadError:continue
                if job['status']!='complete' or not job.get('result'):continue
                result=job['result']
                rows.append({**{k:job[k] for k in ('id','scene_id','filename','kind','created_at')},
                    'class_names':[class_choices()[i]['name'] for i in job['classes']],
                    'duration':result.get('duration',0),'target_count':len(result.get('targets',[])),
                    'poster_url':f"/api/uploads/{job['id']}/assets/{result['poster']}?token={job['asset_token']}"})
        return sorted(rows,key=lambda row:row['created_at'],reverse=True)

    def scene(self,scene_id,owner):
        ident=scene_id.removeprefix('upload-')
        with self._lock:
            job=self._authorized(ident,owner)
            if job['status']!='complete':raise UploadError('not_found')
            return self._result(job)

    def inspect_target(self,scene_id,owner,target,aspects=None):
        from api.target_frames import prepare_target_frames
        return prepare_target_frames(self,scene_id,owner,target,aspects=aspects)

    def cached_answer(self,scene_id,owner,key):
        with self._lock:
            job=self._authorized(scene_id.removeprefix('upload-'),owner)
            path=self._path(job['id'])/'answer-cache.json'
            try:
                if path.stat().st_size>2_000_000:return None
                entries=json.loads(path.read_text(encoding='utf8'))
            except (OSError,ValueError):return None
            row=entries.get(key) if isinstance(entries,dict) else None
            if not isinstance(row,dict) or row.get('revision')!=job['result'].get('revision') or row.get('source')!=job['result'].get('cache_sha256'):return None
            result=deepcopy(row.get('result'))
            if not isinstance(result,dict) or not isinstance(result.get('answer'),str):return None
            allowed={e['id'] for e in job['result']['evidence']}
            if any(c.get('evidence_id') not in allowed for c in result.get('citations',[])):return None
            return {**result,'usage':{'model_calls':0,'tool_calls':0,'input_tokens':0,'output_tokens':0,'usage_complete':True},'tool_calls':[],
                'cache_hit':True,'execution_mode':'cache'}

    def cache_answer(self,scene_id,owner,key,result):
        if not result.get('visual_frame_count') or not result.get('answer') or result.get('error'):return
        with self._lock:
            job=self._authorized(scene_id.removeprefix('upload-'),owner)
            path=self._path(job['id'])/'answer-cache.json'
            try:entries=json.loads(path.read_text(encoding='utf8')) if path.is_file() and path.stat().st_size<2_000_000 else {}
            except (OSError,ValueError):entries={}
            if not isinstance(entries,dict):entries={}
            # Cache canonical results only; no provider messages or image bytes.
            saved={k:v for k,v in result.items() if k not in ('tool_calls','usage')}
            if len(json.dumps(saved,ensure_ascii=False))>120000:return
            entries={k:v for k,v in entries.items() if isinstance(v,dict) and v.get('revision')==job['result'].get('revision')}
            entries[key]={'revision':job['result'].get('revision'),'source':job['result'].get('cache_sha256'),'result':saved}
            entries=dict(list(entries.items())[-12:])
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(entries,ensure_ascii=False),encoding='utf8');temporary.replace(path)

    def asset(self,ident,filename,token):
        with self._lock:
            job=self._read(ident)
            if job['status']!='complete' or not secrets.compare_digest(token,job['asset_token']):raise UploadError('not_found')
            result=job['result'];names={result['media'],result['poster'],*result.get('media_history',[]),*[e['image'] for e in result['evidence']]}
            if result.get('source_media'):names.add(result['source_media'])
            if filename not in names or Path(filename).name!=filename:raise UploadError('not_found')
            path=self._path(ident)/filename
            if not path.is_file():raise UploadError('not_found')
            return path

    def start(self,ident,owner):
        if not self.available():raise UploadError('environment')
        with self._lock:
            job=self._authorized(ident,owner)
            if job['status']!='uploading':return self._public(job)
            source=self._path(ident)/('source'+Path(job['filename']).suffix.lower())
            validate_upload(job['filename'],source.stat().st_size)
            sha=digest(source);pipeline=pipeline_fingerprint()
            for record in self.directory.glob('*/job.json'):
                if record.parent.name==ident:continue
                try:existing=self._read(record.parent.name)
                except UploadError:continue
                if existing.get('owner')==job['owner'] and existing.get('source_sha256')==sha and existing.get('pipeline_fingerprint')==pipeline and sorted(existing.get('initial_classes',existing.get('classes',[])))==sorted(job['classes']) and existing.get('requested_scope')==job.get('requested_scope') and existing['status']=='complete' and not existing.get('updating') and existing.get('result'):
                    self._purge(ident)
                    return {**self._public(existing),'reused_result':True}
            job.update(status='queued',phase='queued',stage='文件已收到，等待分析',source_sha256=sha,pipeline_fingerprint=pipeline)
            self._write(job);self._done[ident]=threading.Event();self._pool.submit(self._run,ident)
            return self._public(job)

    def retry(self,ident,owner):
        if not self.available():raise UploadError('environment')
        with self._lock:
            job=self._authorized(ident,owner)
            if job['status']!='failed':return self._public(job)
            active=sum(1 for event in self._done.values() if not event.is_set())
            if active>=MAX_INFLIGHT:raise UploadError('busy')
            from vision.source_cache import read_source_cache
            try:read_source_cache(self._path(ident),job['source_sha256'])
            except (ValueError,KeyError) as error:raise UploadError('source_expired') from error
            job.update(status='queued',stage='素材已暂存，等待重试',phase='queued',processed=0,total=0,error=None,error_code=None,
                started_at=None,finished_at=None,expires_at=time.time()+RETENTION,manager_pid=os.getpid())
            self._write(job);self._done[ident]=threading.Event();self._pool.submit(self._run,ident)
            return self._public(job)

    def supplement(self,scene_id,owner,classes,on_stage=None):
        try:classes=validate_classes(classes)
        except ValueError as e:raise UploadError('targets') from e
        ident=scene_id.removeprefix('upload-')
        for _ in range(3):
            with self._lock:
                job=self._authorized(ident,owner)
                if job['status']!='complete' or not job['result']:raise UploadError('processing')
                missing=[i for i in classes if i not in job.get('classes',[])]
                if not missing:return self._result(job)
                cache=job['result'].get('cache_file')
                if cache not in ('analysis-source.png','analysis-source.mp4') or not (self._path(ident)/cache).is_file():raise UploadError('source_expired')
                future=self._supplements.get(ident)
                own_batch=not future or future.done()
                if own_batch:
                    active=sum(1 for event in self._done.values() if not event.is_set())
                    if active>=MAX_INFLIGHT:raise UploadError('busy')
                    base=job['result'].get('revision',0)
                    if base<1:raise UploadError('source_expired')
                    self._update(ident,updating=True,stage='等待补充识别',error=None)
                    self._done[ident]=threading.Event()
                    future=self._pool.submit(self._run,ident,missing,base);self._supplements[ident]=future
            if on_stage:on_stage({'stage':'正在补充识别'+ '、'.join(class_choices()[i]['name'] for i in missing)})
            future.result(timeout=MEDIA_WAIT_SECONDS)
            with self._lock:
                finished=self._authorized(ident,owner)
                if all(i in finished.get('classes',[]) for i in classes):return self._result(finished)
                if own_batch:raise UploadError('processing')
        raise UploadError('busy')

    def _run(self,ident,extra_classes=None,base_revision=0):
        directory=self._path(ident);process=None;tree=None;timer=None;error='processing';finished=self._done.get(ident)
        timed_out=threading.Event();began=time.monotonic();current_limit=WORKER_TIMEOUT_SECONDS
        try:
            with self._lock:
                if ident in self._deleted:return
                self._update(ident,**({'updating':True} if base_revision else {'status':'running'}),stage='正在读取你的文件',
                    phase='checking',started_at=time.time(),finished_at=None,error_code=None,timeout_seconds=WORKER_TIMEOUT_SECONDS,eta_seconds=None)
            with (directory/f'worker-r{base_revision+1}.log').open('w',encoding='utf8') as log:
                with self._lock:
                    if ident in self._deleted:return
                    job=self._read(ident)
                    requested=extra_classes if base_revision else job.get('classes',[])
                    process=subprocess.Popen([str(self.python),str(ROOT/'vision/analyze_media.py'),'--directory',str(directory),'--classes',json.dumps(requested),'--base-revision',str(base_revision),'--scope',json.dumps(job.get('requested_scope'))],
                        cwd=ROOT,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf8',errors='replace',env=vision_environment(),
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0,start_new_session=sys.platform!='win32')
                    tree=ProcessTree(process);self._processes[ident]=tree
                def expire():
                    timed_out.set();tree.kill()
                timer=threading.Timer(WORKER_TIMEOUT_SECONDS,expire);timer.daemon=True;timer.start()
                for line in process.stdout:
                    try:item=json.loads(line)
                    except ValueError:continue
                    if item.get('stage')=='error':error=item.get('code','processing')
                    if item.get('stage') in STAGES:
                        processed=max(0,min(MAX_VIDEO_FRAMES,int(item.get('processed',0))));total=max(0,min(MAX_VIDEO_FRAMES,int(item.get('total',0))))
                        if item.get('stage')=='loading' and item.get('device') is not None:
                            limit=MEDIA_LIMITS['fast_worker_timeout_seconds'] if item['device']!='cpu' or total<=SAMPLE_SHORT_FRAMES else WORKER_TIMEOUT_SECONDS
                            if limit!=current_limit:
                                timer.cancel();current_limit=limit
                                timer=threading.Timer(max(.01,limit-(time.monotonic()-began)),expire);timer.daemon=True;timer.start()
                        eta=None;elapsed=float(item.get('detection_elapsed_seconds') or 0)
                        if item['stage']=='detecting' and 10<=processed<total and 0<elapsed<WORKER_TIMEOUT_SECONDS:
                            remaining=(total-processed)*elapsed/processed
                            eta={'low':max(1,round(remaining*.7)),'high':max(2,round(remaining*1.5+max(5,total*.04)))}
                        self._update(ident,stage=STAGES[item['stage']],phase=item['stage'],processed=processed,total=total,timeout_seconds=current_limit,eta_seconds=eta)
                if process.wait()!=0:raise UploadError('timeout' if timed_out.is_set() else error)
                timer.cancel()
            result=json.loads((directory/f'result-r{base_revision+1}.json').read_text(encoding='utf8'))
            job=self._read(ident)
            if base_revision:
                existing_ids={e['id'] for e in result['evidence']}
                result['evidence'].extend(e for e in job['result']['evidence'] if e.get('image','').startswith('view-r') and e['id'] not in existing_ids)
            model=json.loads((ROOT/'vision/upload-model.lock.json').read_text(encoding='utf8'))
            if result['source_sha256']!=job['source_sha256'] or result['model_sha256']!=model['sha256'] or result['id']!=job['scene_id']:raise UploadError('processing')
            classes=list(dict.fromkeys([*job.get('classes',[]),*(extra_classes or [])]))
            if result['kind']=='video':
                if result.get('processing',{}).get('tracking_policy_sha256')!=digest(ROOT/'vision/upload-tracking.json'):raise UploadError('version')
                if result.get('processing',{}).get('detection_policy_sha256')!=digest(ROOT/'vision/upload-detection.json'):raise UploadError('version')
                if 0 in classes:
                    appearance=json.loads((ROOT/'vision/appearance-model.lock.json').read_text(encoding='utf8'))
                    if result['processing'].get('appearance_model_sha256')!=appearance['sha256']:raise UploadError('processing')
            allowed={class_choices()[i]['label'] for i in classes}
            if result.get('revision')!=base_revision+1 or result.get('classes',[])!=classes or set(result.get('class_labels',[]))!=allowed or any(t['label'] not in allowed for t in result['targets']) or any(c['label'] not in allowed for c in result['counts']):raise UploadError('processing')
            if base_revision and result.get('cache_sha256')!=job['result'].get('cache_sha256'):raise UploadError('processing')
            assets={result['media'],result['poster'],*result.get('media_history',[]),*[e['image'] for e in result['evidence']]}
            expected_source='analysis-source.png' if result['kind']=='image' else 'analysis-source.mp4'
            if result.get('source_media')!=expected_source:raise UploadError('processing')
            assets.add(expected_source)
            if any(Path(n).name!=n or Path(n).suffix not in ('.jpg','.webm','.png','.mp4') or not (directory/n).is_file() for n in assets):raise UploadError('processing')
            self._update(ident,status='complete',updating=False,stage='分析完成',phase='complete',finished_at=time.time(),classes=classes,result=result,error=None,error_code=None,expires_at=None)
        except Exception as e:
            error=e.code if isinstance(e,UploadError) else error
            message=ERROR_MESSAGES.get(error,ERROR_MESSAGES['processing'])
            if error=='timeout':message=f'分析达到{current_limit//60}分钟处理上限，尚未完成。可重试当前素材，或选择较短片段。'
            try:self._update(ident,status='complete' if base_revision else 'failed',updating=False,finished_at=time.time(),expires_at=None if base_revision else time.time()+RETENTION,error_code=error,stage='补充识别未完成，原结果已保留' if base_revision else '这次分析未完成',error=message)
            except UploadError:pass
        finally:
            if timer:timer.cancel()
            if tree:
                if process.poll() is None:tree.kill()
                tree.close()
            elif process is not None and process.poll() is None:process.kill();process.wait()
            try:
                with self._lock:
                    self._processes.pop(ident,None)
                    if directory.is_dir():
                        for p in directory.glob('source.*'):p.unlink(missing_ok=True)
                        for name in ('normalized.mp4','render.avi'): (directory/name).unlink(missing_ok=True)
                        if (directory/'samples').is_dir():self._remove(directory/'samples',parent=directory)
                    if ident in self._deleted:self._purge(ident);self._deleted.discard(ident)
            finally:
                if finished:finished.set()

    def _remove(self,path,parent=None):
        resolved=Path(path).resolve();expected=Path(parent or self.directory).resolve()
        if resolved.parent!=expected or expected!=self.directory and expected.parent!=self.directory:raise UploadError('not_found')
        if resolved.is_dir():shutil.rmtree(resolved)

    def delete(self,ident,owner):
        with self._lock:
            self._authorized(ident,owner);self._deleted.add(ident)
            tree=self._processes.get(ident);done=self._done.get(ident)
            if tree:tree.kill()
            else:self._purge(ident);self._deleted.discard(ident)
        if tree and (not done or not done.wait(8) or self._path(ident).exists()):raise UploadError('processing')

    def _purge(self,ident):
        if self.on_remove:self.on_remove('upload-'+ident)
        self._remove(self._path(ident))
        self._done.pop(ident,None)
        self._supplements.pop(ident,None)

    def cleanup(self):
        with self._lock:
            for record in self.directory.glob('*/job.json'):
                try:
                    job=json.loads(record.read_text(encoding='utf8'));ident=record.parent.name
                    if job['status']=='complete' and job.get('result'):
                        if job.get('expires_at') is not None:job['expires_at']=None;self._write(job)
                        continue
                    interrupted=job['status'] in ('uploading','queued','running') and not pid_alive(job.get('manager_pid'))
                    if job['expires_at']>time.time() and not interrupted:continue
                    if ident in self._processes or ident in self._supplements and not self._supplements[ident].done():continue
                    if ident in self._done and not self._done[ident].is_set() and job.get('manager_pid')==os.getpid():continue
                    self._purge(ident)
                except Exception:continue # Retry cleanup on the next interval; never expose private job contents.

    def start_cleanup(self):
        def loop():
            self.cleanup()
            while not self._stopping.wait(60):self.cleanup()
        threading.Thread(target=loop,daemon=True,name='media-expiry').start()

    def close(self):
        self._stopping.set()
        with self._lock:
            for tree in self._processes.values():tree.kill()
        self._pool.shutdown(wait=False,cancel_futures=True)
