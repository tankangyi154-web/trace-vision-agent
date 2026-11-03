"""Choose a CPU path from a short local comparison; profiles never leave this machine."""
import hashlib,json,os,platform,sys,time

def cpu_threads():
    available=os.cpu_count() or 1
    if sys.platform=='win32':
        try:
            import ctypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetCurrentProcess.restype=ctypes.c_void_p
            kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
            mask=ctypes.c_size_t();system=ctypes.c_size_t()
            if kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(),ctypes.byref(mask),ctypes.byref(system)):available=min(available,mask.value.bit_count())
        except (OSError,AttributeError):pass
    elif hasattr(os,'sched_getaffinity'):available=min(available,len(os.sched_getaffinity(0)))
    return max(1,min(4,available))

def prefer_onnx(models,root):
    import cv2,torch
    from ultralytics import YOLO
    from vision.onnx_cpu import OnnxDetector
    from vision.appearance import PersonAppearance
    from vision.media_detection import MediaDetector
    from pathlib import Path
    key=hashlib.sha256(json.dumps([platform.processor(),os.cpu_count(),cpu_threads(),torch.__version__,models['onnxruntime'],models['detector']['sha256'],models['appearance']['sha256']]).encode()).hexdigest()
    path=root/'work/cpu-profile.json'
    try:
        cached=json.loads(path.read_text(encoding='utf8'))
        if cached.get('hardware_key')==key:return cached.get('backend')=='onnxruntime-cpu'
    except (OSError,ValueError):pass
    cap=cv2.VideoCapture(str(root/'web/public/media/presets/daylight/analysis-source.mp4'));frames=[]
    for _ in range(3):
        ok,frame=cap.read()
        if ok:frames.append(frame)
    cap.release()
    if len(frames)!=3:return False
    lock=json.loads((root/'vision/upload-model.lock.json').read_text(encoding='utf8'));timings={}
    for name in ['pytorch-cpu','onnxruntime-cpu']:
        model=YOLO(str(root/'vision/weights'/lock['model'])) if name=='pytorch-cpu' else OnnxDetector(models['detector_session'])
        encoder=PersonAppearance() if name=='pytorch-cpu' else PersonAppearance(session=models['appearance_session'])
        detector=MediaDetector(model,lock,[0,2,1],'video',100,5,device='cpu')
        started=time.perf_counter()
        for frame in frames:
            result=detector(frame)
            people=result.boxes.data.cpu().numpy();encoder(frame,people[people[:,5]==0,:4])
        timings[name]=round(time.perf_counter()-started,4)
    backend='onnxruntime-cpu' if timings['onnxruntime-cpu']<timings['pytorch-cpu']*.95 else 'pytorch-cpu'
    profile={'hardware_key':key,'backend':backend,'threads':cpu_threads(),'frames':len(frames),'timings_seconds':timings,'scope':'local warmup comparison; not a universal speed guarantee'}
    try:
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(profile,indent=2),encoding='utf8');temporary.replace(path)
    except OSError:pass
    return backend=='onnxruntime-cpu'
