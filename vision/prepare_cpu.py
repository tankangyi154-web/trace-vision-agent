"""Export fixed local weights in a short temporary path; verify before enabling CPU ONNX."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def export_and_check(tools):
    sys.path.insert(0,str(tools))
    os.environ['YOLO_CONFIG_DIR']=str(ROOT/'work/cpu-export-yolo');os.environ['YOLO_OFFLINE']='true'
    import numpy as np
    import cv2,onnx,torch
    from ultralytics import YOLO
    from vision.appearance import PersonAppearance
    from vision.onnx_cpu import session,OnnxDetector,digest
    torch.set_num_threads(4)
    directory=ROOT/'work/onnx-models';directory.mkdir(parents=True,exist_ok=True)
    (directory/'manifest.json').unlink(missing_ok=True)
    detector_lock=json.loads((ROOT/'vision/upload-model.lock.json').read_text())
    appearance_lock=json.loads((ROOT/'vision/appearance-model.lock.json').read_text())
    model_path=ROOT/'vision/weights'/detector_lock['model']
    if digest(model_path)!=detector_lock['sha256']:raise ValueError('Detector weight checksum mismatch')
    model=YOLO(str(model_path))
    exported=Path(model.export(format='onnx',imgsz=960,opset=17,simplify=False,dynamic=True,half=False,device='cpu',batch=1))
    exported.replace(directory/'detector.onnx')
    appearance=PersonAppearance()
    torch.onnx.export(appearance.model,torch.zeros(2,3,appearance_lock['input_height'],appearance_lock['input_width']),str(directory/'appearance.onnx'),
        input_names=['images'],output_names=['features'],dynamic_axes={'images':{0:'batch'},'features':{0:'batch'}},opset_version=17,dynamo=False)
    for name in ['detector','appearance']:onnx.checker.check_model(onnx.load(str(directory/(name+'.onnx'))))
    onnx_detector=OnnxDetector(session(directory/'detector.onnx'))
    onnx_appearance=PersonAppearance(session=session(directory/'appearance.onnx'))
    cap=cv2.VideoCapture(str(ROOT/'web/public/media/presets/daylight/analysis-source.mp4'));ok,image=cap.read();cap.release()
    if not ok:raise RuntimeError('Packaged verification example is missing')
    checks=[]
    for size in [960,1280]:
        before=model.predict(image,imgsz=size,conf=.25,iou=.65,classes=[0,2,1],device='cpu',half=False,verbose=False)[0].boxes.data.cpu().numpy()
        after=onnx_detector.predict(image,imgsz=size,conf=.25,iou=.65,classes=[0,2,1])[0].boxes.data.numpy()
        if len(before)!=len(after):raise RuntimeError('CPU export changes detection count')
        overlaps=[]
        for row in before:
            candidates=after[after[:,5]==row[5]]
            if not len(candidates):raise RuntimeError('CPU export changes detection class')
            intersection=np.prod(np.maximum(0,np.minimum(row[2:4],candidates[:,2:4])-np.maximum(row[:2],candidates[:,:2])),axis=1)
            union=np.prod(row[2:4]-row[:2])+np.prod(candidates[:,2:4]-candidates[:,:2],axis=1)-intersection
            overlaps.append(float(np.max(intersection/union)))
        if min(overlaps,default=1)<.99:raise RuntimeError('CPU export changes box geometry')
        checks.append({'imgsz':size,'boxes':len(before),'minimum_matched_iou':min(overlaps,default=1)})
    boxes=before[before[:,5]==0,:4]
    baseline=appearance(image,boxes);optimized=onnx_appearance(image,boxes)
    differences=[float(abs(1-np.dot(a['feature'],b['feature']))) for a,b in zip(baseline,optimized) if a['feature'] is not None]
    if max(differences,default=0)>1e-5:raise RuntimeError('CPU export changes appearance features')
    import onnxruntime
    data={'version':'onnx-fp32-v1','verified':True,'enabled':True,'precision':'float32','cpu_threads':4,'opset':17,'onnxruntime':onnxruntime.__version__,
        'detector':{'source_sha256':detector_lock['sha256'],'sha256':digest(directory/'detector.onnx')},
        'appearance':{'source_sha256':appearance_lock['sha256'],'sha256':digest(directory/'appearance.onnx')},
        'numerical_smoke_check':{'frames':1,'detector':checks,'maximum_appearance_cosine_distance':max(differences,default=0)}}
    (directory/'manifest.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf8')
    print(json.dumps(data,indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--export-tools',type=Path);parser.add_argument('--force',action='store_true');args=parser.parse_args()
    if args.export_tools:export_and_check(args.export_tools);return
    from vision.onnx_cpu import verified_models
    if not args.force and verified_models(require_enabled=False):print('Verified CPU model candidate is ready.');return
    # ONNX's upstream test data contains long filenames. Keep export-only tooling out of the deep project path.
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'Temp' if sys.platform=='win32' else Path(tempfile.gettempdir())
    base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trace-onnx-',dir=base) as tools:
        subprocess.run([sys.executable,'-m','pip','install','--target',tools,'onnx==1.19.1','--constraint',str(ROOT/'vision/requirements.lock.txt'),'--disable-pip-version-check'],check=True)
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--export-tools',tools],check=True,cwd=ROOT)

if __name__=='__main__':main()
