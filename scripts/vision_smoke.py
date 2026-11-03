"""One actual local frame verifies native libraries, models, tracking and CPU selection."""
from pathlib import Path
import hashlib,json,os,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    started=time.perf_counter()
    os.environ['YOLO_CONFIG_DIR']=str(ROOT/'work/smoke-yolo');os.environ['YOLO_OFFLINE']='true'
    report={'ok':False,'model_calls':0}
    try:
        import cv2,torch,yaml
        from ultralytics import YOLO
        from vision.cpu_calibration import cpu_threads
        from vision.onnx_cpu import verified_models,OnnxDetector
        from vision.appearance import PersonAppearance
        from vision.media_detection import MediaDetector
        from vision.media_tracking import create_trackers,tracked_detections
        torch.set_num_threads(cpu_threads())
        from api.runtime import inspect_runtime
        if not inspect_runtime(ROOT,check_self_test=False)['video_analysis']:raise RuntimeError('Model, interpreter or FFmpeg missing')
        cap=cv2.VideoCapture(str(ROOT/'web/public/media/presets/daylight/analysis-source.mp4'));ok,frame=cap.read();cap.release()
        if not ok:raise RuntimeError('Verification example cannot be decoded')
        models=verified_models()
        lock=json.loads((ROOT/'vision/upload-model.lock.json').read_text(encoding='utf8'))
        model=OnnxDetector(models['detector_session']) if models else YOLO(str(ROOT/'vision/weights'/lock['model']))
        encoder=PersonAppearance(session=models['appearance_session'] if models else None)
        detector=MediaDetector(model,lock,[0,2,1],'video',79,5,device='cpu')
        trackers=create_trackers([0,2,1],yaml.safe_load((ROOT/'vision/bytetrack.yaml').read_text()),encoder)
        visible,ids=tracked_detections(trackers,detector(frame).boxes,frame)
        if not len(ids) or len(ids)!=len(visible):raise RuntimeError('No usable detections or tracking IDs')
        report.update(ok=True,device='cpu',backend='onnxruntime-cpu' if models else 'pytorch-cpu',threads=cpu_threads(),tracked_boxes=len(ids))
    except (ImportError,OSError) as error:
        report.update(code='native_runtime',reason='本机图像分析运行库未能载入。已有示例仍可查看，请运行环境检查。',exception_type=type(error).__name__)
    except Exception as error:
        report.update(code='vision_self_test',reason='本机识别自检未通过。已有示例仍可查看，请运行环境检查。',exception_type=type(error).__name__)
    report['elapsed_seconds']=round(time.perf_counter()-started,3)
    (ROOT/'work').mkdir(exist_ok=True)
    (ROOT/'work/vision-selftest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
