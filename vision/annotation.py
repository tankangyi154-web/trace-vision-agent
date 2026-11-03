"""Type colors and compact labels placed around, rather than across, objects."""
import json
from pathlib import Path

STYLE=json.loads((Path(__file__).resolve().parents[1]/'data/annotation-style.json').read_text(encoding='utf8'))

def class_color(label):
    return STYLE['colors'].get(label,STYLE['fallback_palette'][sum(map(ord,label))%len(STYLE['fallback_palette'])])

def annotation_text(box,label_name):
    return f"{label_name(box['label'])} #{box['id']}"

def overlap(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))

def label_positions(boxes,width,height,text_width):
    """Deterministic candidates; label collisions cost more than a short leader line."""
    if min(width,height)<40:return []
    import numpy as np
    placed=[];output=[];h=STYLE['label_height']
    pixels=[[v*d for v,d in zip(b['bbox'],(width,height,width,height))] for b in boxes]
    all_pixels=np.asarray(pixels,dtype=np.float64).reshape(-1,4)
    def intersections(candidates,rectangles):
        lengths=np.maximum(0,np.minimum(candidates[:,None,2:],rectangles[None,:,2:])-np.maximum(candidates[:,None,:2],rectangles[None,:,:2]))
        return lengths[:,:,0]*lengths[:,:,1]
    for own,(box,rect) in enumerate(zip(boxes,pixels)):
        x1,y1,x2,y2=rect;w=min(width-4,text_width(box)+12)
        candidates=[]
        for dy in [0,-h,h,-2*h,2*h,-3*h,3*h,-4*h,4*h]:
            for x,y in [(x1,y1-h-4+dy),(x1,y2+4+dy),(x2+5,y1+dy),(x1-w-5,y1+dy)]:
                x=max(2,min(width-w-2,x));y=max(2,min(height-h-2,y))
                candidate=[x,y,x+w,y+h]
                candidates.append(candidate)
        array=np.asarray(candidates,dtype=np.float64)
        weights=np.full(len(boxes),12.);weights[own]=4.
        costs=(intersections(array,all_pixels)*weights).sum(axis=1)
        if placed:costs+=intersections(array,np.asarray(placed)).sum(axis=1)*1000
        costs+=np.abs(array[:,0]-x1)+np.abs(array[:,1]-(y1-h-4))
        label=candidates[int(np.argmin(costs))];placed.append(label)
        output.append({'box':box,'rect':rect,'label_rect':label,'color':class_color(box['label'])})
    return output

def annotate(frame,boxes,label_name):
    import cv2
    import numpy as np
    from PIL import Image,ImageDraw,ImageFont
    # Enlarging is for legible exported text; it does not restore source detail.
    height,width=frame.shape[:2];factor=max(1,min(960/width,960/height))
    if factor>1:frame=cv2.resize(frame,(round(width*factor),round(height*factor)),interpolation=cv2.INTER_CUBIC)
    height,width=frame.shape[:2]
    image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));draw=ImageDraw.Draw(image)
    font_file=Path('C:/Windows/Fonts/msyh.ttc')
    font=ImageFont.truetype(str(font_file),STYLE['font_size']) if font_file.is_file() else ImageFont.load_default()
    layout=label_positions(boxes,width,height,lambda b:draw.textlength(annotation_text(b,label_name),font=font))
    for item in layout:
        draw.rectangle(item['rect'],outline='#ffffff',width=3)
        draw.rectangle(item['rect'],outline=item['color'],width=2)
    for item in layout:
        x1,y1,x2,y2=item['rect'];x,y,right,bottom=item['label_rect'];color=item['color']
        anchor=(max(x1,min(x2,(x+right)/2)),y1)
        end=(max(x,min(right,anchor[0])),max(y,min(bottom,anchor[1])))
        draw.line((anchor,end),fill=color,width=1)
        draw.rounded_rectangle((x,y,right,bottom),radius=3,fill=color)
        text=annotation_text(item['box'],label_name);bounds=draw.textbbox((0,0),text,font=font)
        draw.text((x+6,y+(STYLE['label_height']-(bounds[3]-bounds[1]))/2-bounds[1]),text,font=font,fill='white')
    return cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
