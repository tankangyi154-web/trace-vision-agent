"""FP32 CPU execution with the same preprocessing, suppression and track inputs."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def session(path):
    import onnxruntime as ort
    from vision.cpu_calibration import cpu_threads
    options=ort.SessionOptions();options.intra_op_num_threads=cpu_threads();options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.add_session_config_entry('session.intra_op.allow_spinning','0')
    options.add_session_config_entry('session.inter_op.allow_spinning','0')
    return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])

def verified_models(root=None,require_enabled=True):
    root=Path(root or ROOT);directory=root/'work/onnx-models'
    try:
        data=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
        if data.get('version')!='onnx-fp32-v1' or data.get('verified') is not True:return None
        if require_enabled and data.get('enabled') is not True:return None
        for name,lock in [('detector','upload-model.lock.json'),('appearance','appearance-model.lock.json')]:
            source=json.loads((root/'vision'/lock).read_text(encoding='utf8'))
            if data[name]['source_sha256']!=source['sha256'] or data[name]['sha256']!=digest(directory/(name+'.onnx')):return None
        models={**data,'detector_session':session(directory/'detector.onnx'),'appearance_session':session(directory/'appearance.onnx')}
        if require_enabled:
            from vision.cpu_calibration import prefer_onnx
            if not prefer_onnx(models,root):return None
        return models
    except (OSError,ValueError,KeyError,TypeError,ImportError,RuntimeError):return None

class OnnxDetector:
    def __init__(self,inference_session):
        from vision.analyze_media import NAMES
        self.session=inference_session
        self.names={i:label.replace('_',' ') for i,label in enumerate(NAMES)}

    def predict(self,frame,*,conf=.25,iou=.5,imgsz=960,max_det=200,classes=None,**kwargs):
        import numpy as np
        import torch
        from ultralytics.data.augment import LetterBox
        from ultralytics.utils import nms,ops
        from ultralytics.engine.results import Results
        image=LetterBox((imgsz,imgsz),auto=True,stride=32)(image=frame)
        image=np.ascontiguousarray(image[:,:,::-1].transpose(2,0,1)[None]).astype(np.float32)/255
        output=self.session.run(None,{self.session.get_inputs()[0].name:image})[0]
        boxes=nms.non_max_suppression(torch.from_numpy(output),conf,iou,classes,max_det=max_det)[0]
        boxes[:,:4]=ops.scale_boxes(image.shape[2:],boxes[:,:4],frame.shape)
        return [Results(frame,path='',names=self.names,boxes=boxes[:,:6])]
