"""Bounded extra detail for dense scenes; use the same local pinned detector."""
import json
from pathlib import Path

POLICY_PATH=Path(__file__).with_name('upload-detection.json')
POLICY=json.loads(POLICY_PATH.read_text(encoding='utf8'))


def normalization_bounds(width,height,duration):
    if duration<=POLICY['detail_max_seconds']:
        long,short=POLICY['detail_long_edge'],POLICY['detail_short_edge']
        return (long,short) if width>=height else (short,long)
    return 1280,960


def dense_candidates(rows):
    strong=[r for r in rows if r[4]>=.25]
    return sum(int(r[5])==0 for r in strong)>=POLICY['dense_people_trigger'] or len(strong)>=POLICY['dense_objects_trigger']


class MediaDetector:
    def __init__(self,model,lock,classes,kind,total,sample_fps,device='cpu'):
        self.model=model;self.lock=lock;self.classes=classes;self.kind=kind
        self.detail=kind=='image' or total<=POLICY['detail_max_seconds']*sample_fps
        self.dense=False;self.dense_frames=0;self.extra_passes=0
        self.options={}
        self.device=device

    def _predict(self,frame):
        self.options={'conf':self.lock['detector_confidence'] if self.kind=='video' else self.lock['image_confidence'],
            'iou':POLICY['dense_iou'] if self.dense else self.lock['iou'],
            'imgsz':POLICY['dense_imgsz'] if self.dense and self.detail else self.lock['imgsz'],
            'max_det':POLICY['max_detections'],'device':self.device,'half':False,'verbose':False,'classes':self.classes}
        return self.model.predict(frame,**self.options)[0]

    def __call__(self,frame):
        result=self._predict(frame)
        if not self.dense and dense_candidates(result.boxes.data.tolist()):
            self.dense=True;self.extra_passes+=1
            result=self._predict(frame)
        if self.dense:self.dense_frames+=1
        return result
