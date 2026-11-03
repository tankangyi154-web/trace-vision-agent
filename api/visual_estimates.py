"""Validate explicitly approximate visual estimates, separate from measurements."""
import re


def height_estimate(row,frames):
    estimate=row.get('height_estimate')
    if estimate is None:return None
    if row.get('aspect')!='height' or row.get('status')!='uncertain' or not isinstance(estimate,dict):
        raise ValueError('目测身高必须单独标记为uncertain，不能当作测量结果。')
    interval=estimate.get('range_cm');reference=estimate.get('reference',{})
    if not isinstance(interval,list) or len(interval)!=2 or any(type(n) is not int for n in interval) or not 50<=interval[0]<interval[1]<=250 or not 10<=interval[1]-interval[0]<=40:
        raise ValueError('目测身高应给至少十厘米宽的合理范围，不能报精确单点数字。')
    if estimate.get('full_body_visible') is not True or not isinstance(reference,dict) or not (reference.get('same_ground_plane') is True or reference.get('same_depth_plane') is True):
        raise ValueError('只有头脚完整、站姿可见且参照与人物处于相近距离时才能粗估身高。')
    label=reference.get('name');ref_range=reference.get('height_cm')
    if not isinstance(label,str) or not 4<=len(label)<=60 or not re.search(r'门|椅|座|栏杆|护栏|台阶|交通锥|垃圾桶|桌|车轮|轮胎|纸张|打印纸|白纸|标尺',label):
        raise ValueError('请明确画面中可见的具体尺寸参照，不能只按成年人平均身高或人体比例猜数值。')
    if re.search(r'https?://|token|/api/|\d|[一二三四五六七八九十]+(?:米|厘米)',label,re.I):raise ValueError('参照名称不能包含内部地址或未经结构化的尺寸数字。')
    if not isinstance(ref_range,list) or len(ref_range)!=2 or any(type(n) is not int for n in ref_range) or not 20<=ref_range[0]<ref_range[1]<=300 or ref_range[1]-ref_range[0]>80:
        raise ValueError('必须明确参照物常见高度的假设范围，而不是声称知道它的真实尺寸。')
    own=[f for f in frames if f['evidence_id'] in row.get('evidence_ids',[])]
    usable=[f for f in own if f.get('pixels',[0,0])[1]>=180 and len(f.get('bbox',[]))==4 and min(f['bbox'][0],f['bbox'][1],1-f['bbox'][2],1-f['bbox'][3])>=.01 and not set(f.get('flags',[]))&{'blurred','overlapping_boxes','touching_frame_edge'}]
    if not usable:raise ValueError('本项引用中没有清晰、完整且未严重遮挡的人体画面，不能粗估身高。')
    text=f"粗略目测约{interval[0]}—{interval[1]}厘米，参照{label}的常见高度；受距离和视角影响，仅作目测参考。"
    return text,{'range_cm':interval,'reference':reference,'method':'approximate_visual_reference','not_a_measurement':True}
