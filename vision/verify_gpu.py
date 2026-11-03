"""Enable the isolated CUDA environment only after a real inference smoke test."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    import numpy as np
    import torch
    from ultralytics import YOLO
    from vision.device import inference_device
    from vision.appearance import PersonAppearance
    destination=ROOT/'work/vision-gpu-env/ready.json'
    if Path(sys.prefix).resolve()!=destination.parent.resolve():raise RuntimeError('Run with work/vision-gpu-env Python')
    destination.unlink(missing_ok=True)
    device=inference_device()
    if device=='cpu':raise RuntimeError('No usable CUDA device; CPU environment remains available')
    image=np.full((160,160,3),128,dtype=np.uint8)
    YOLO(str(ROOT/'vision/weights/yolo11s.pt')).predict(image,device=device,half=False,verbose=False)
    profile=PersonAppearance(device=device)(image,[[10,10,80,150]])
    if profile[0]['feature'] is None or not np.isfinite(profile[0]['feature']).all():raise RuntimeError('Appearance smoke test failed')
    data={'cuda_smoke_test':True,'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)}
    destination.write_text(json.dumps(data,indent=2),encoding='utf8')
    print(json.dumps(data))

if __name__=='__main__':main()
