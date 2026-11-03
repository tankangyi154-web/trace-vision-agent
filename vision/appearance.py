"""Pinned, local-only clothing/body embeddings. No identity database or face lookup."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class PersonAppearance:
    def __init__(self,device='cpu',session=None,optimize_cpu=True):
        import torch
        import numpy as np
        from vision.vendor.osnet import OSNet,OSBlock
        self.lock=json.loads((ROOT/'vision/appearance-model.lock.json').read_text(encoding='utf8'))
        path=ROOT/'vision/weights'/self.lock['model']
        for file,expected in [(path,self.lock['sha256']),(ROOT/'vision/vendor/osnet.py',self.lock['architecture_sha256'])]:
            with file.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=expected:raise ValueError('environment')
        self.device=device
        self.session=session
        self.model=None
        if session is None:
            state=torch.load(path,map_location='cpu',weights_only=True)
            self.model=OSNet(num_classes=state['classifier.weight'].shape[0],blocks=[OSBlock]*3,layers=[2]*3,channels=[16,64,96,128])
            self.model.load_state_dict(state,strict=True);self.model.eval();self.model.to(device)
            if device=='cpu' and optimize_cpu:
                # Fold frozen BatchNorm into Conv2d. Weights and FP32 semantics are preserved.
                for module in self.model.modules():
                    if isinstance(getattr(module,'conv',None),torch.nn.Conv2d) and isinstance(getattr(module,'bn',None),torch.nn.BatchNorm2d):
                        module.conv=torch.nn.utils.fuse_conv_bn_eval(module.conv,module.bn)
                        module.bn=torch.nn.Identity()
        self.mean=np.array([.485,.456,.406],dtype=np.float32)[:,None,None]
        self.std=np.array([.229,.224,.225],dtype=np.float32)[:,None,None]

    def __call__(self,frame,boxes):
        import cv2
        import numpy as np
        import torch
        h,w=frame.shape[:2];items=[];inputs=[];valid=[]
        for i,(x1,y1,x2,y2) in enumerate(boxes):
            left=max(0,min(w-1,int(x1)));top=max(0,min(h-1,int(y1)))
            right=max(left+1,min(w,int(x2+.999)));bottom=max(top+1,min(h,int(y2+.999)))
            crop=frame[top:bottom,left:right];ch,cw=crop.shape[:2]
            item={'feature':None,'color':None,'reliable':cw>=5 and ch>=14,'occluded':False}
            if item['reliable']:
                rgb=cv2.cvtColor(cv2.resize(crop,(self.lock['input_width'],self.lock['input_height'])),cv2.COLOR_BGR2RGB)
                inputs.append((rgb.astype(np.float32).transpose(2,0,1)/255-self.mean)/self.std);valid.append(i)
                torso=crop[max(0,int(ch*.15)):max(1,int(ch*.62)),int(cw*.2):max(int(cw*.2)+1,int(cw*.8))]
                hsv=cv2.cvtColor(torso,cv2.COLOR_BGR2HSV)
                # Saturation-aware histogram retains both colored and neutral clothing.
                hist=cv2.calcHist([hsv],[0,1],None,[12,4],[0,180,0,256]).ravel()
                item['color']=hist/max(float(hist.sum()),1)
            items.append(item)
        for start in range(0,len(inputs),32):
            array=np.stack(inputs[start:start+32])
            if self.session is not None:
                features=self.session.run(None,{self.session.get_inputs()[0].name:array})[0]
                features=features/np.maximum(np.linalg.norm(features,axis=1,keepdims=True),1e-12)
            else:
                batch=torch.from_numpy(array).to(self.device)
                with torch.inference_mode():features=torch.nn.functional.normalize(self.model(batch),dim=1).cpu().numpy()
            for index,feature in zip(valid[start:start+32],features):items[index]['feature']=feature
        for i,a in enumerate(boxes):
            for j,b in enumerate(boxes):
                if i==j:continue
                intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                area=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
                if area>0 and intersection/area>.25:items[i]['occluded']=True
        return items
