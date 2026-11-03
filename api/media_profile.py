"""Bounded, plain-language facts from actual uploaded tracking samples."""
import math
import re

LIMITS={
    'gender':'性别：不能从这份检测记录可靠判断。',
    'body':'体型：当前系统没有可靠的体型分析结果。',
    'height':'身高：没有已知尺寸的参照数据，无法可靠估计身高。',
    'action':'具体行为：位置记录不能可靠说明它正在做什么。',
    'speed':'真实速度：没有距离与尺度标定，无法可靠估计。',
    'distance':'真实距离：没有尺度标定，无法可靠估计。',
    'identity':'真实身份：片段编号不能确定人物姓名或真实身份。',
}
VISUAL_LABELS={'gender':'性别','body':'体型','height':'身高','action':'动作','clothing':'衣着','appearance':'可见外观','carrying':'随身物品'}
PATTERNS={
    'duration':r'(?:出现|停留|驻留|识别|看见)(?:了|持续|累计|大概|大约|总共|一共|时间|时长)*\s*(?:多久|多长时间|多少秒|几秒钟?)|出现时长|累计时长',
    'presence':r'首次|最早|出现时间|(?:什么时候|什么时间|何时|几秒).*出现|出现.*(?:什么时候|什么时间|何时|几秒)',
    'trajectory':r'轨迹|路线|路径|往哪|去哪|位置变化|移动方向|怎么走|走向',
    'visibility':r'消失|离开|不见|没(?:有)?(?:被)?识别|中断|跟丢|最后(?:一次)?(?:识别|出现|看见|看到)|看不见',
    'gender':r'性别|男性|女性|男的|女的|男还是女|男女|男生|女生',
    'body':r'身材|体型|身形|身型|体态|胖瘦|胖|瘦',
    'height':r'身高|多高|高多少|几米高|高矮',
    'action':r'做什么|做了什么|在做|什么动作|在干嘛|在干什么|具体行为|动作|姿态|姿势|走路|跑步|骑车',
    'speed':r'速度|时速|多快|航速|车速',
    'distance':r'距离|多远|走了.*米|移动.*米',
    'identity':r'他是谁|她是谁|身份|名字|姓名',
    'clothing':r'衣服|衣着|穿着|穿什么|穿的|穿了|上衣|裤子|颜色|着装',
    'appearance':r'外观|长什么样|样貌|外貌|长相|发型|胡须|眼镜|特征|描述.*(?:人|目标)|分析.*(?:人|目标)',
    'carrying':r'拿着|拿什么|手里|手上|携带|背着|背什么|提着|随身',
}

def question_plan(question):
    targets=[]
    for match in re.finditer(r'(?:目标|行人|人|汽车|车辆|物体|船)\s*#?\s*(\d+)(?![\d.])(?!\s*(?:秒|分|米|岁))\s*号?|#\s*(\d+)(?![\d.])|(?<![\d.])(\d+)\s*号',question):
        ident=str(int(next(g for g in match.groups() if g is not None)))
        if ident not in targets:targets.append(ident)
    facets=[]
    clauses=re.split(r'[，,；;。！？!?\n]',question)
    for facet,pattern in PATTERNS.items():
        for clause in clauses:
            match=re.search(pattern,clause)
            if match and not re.search(r'不要|不用|无需|不必|别猜',clause[:match.start()][-12:]):
                facets.append(facet);break
    if 'duration' in facets and 'presence' in facets and not re.search(r'首次|第一次|最早|什么时候|什么时间|何时|出现时间|第几秒',question):facets.remove('presence')
    plan={'targets':targets,'facets':facets}
    if 'duration' in facets and re.search(r'连续|不间断',question) and not re.search(r'累计|总共',question):
        facets[facets.index('duration')]='continuous_duration'
    rankings=[]
    for clause in clauses:
        if not re.search(r'(?:出现|停留|驻留|待).*?最(?:长|久)|最(?:长|久).*?(?:出现|停留|驻留)',clause):continue
        if not re.search(r'谁|哪|分别|编号.*?(?:几|多少)|最[长久]的',clause):continue
        metric='longest_interval_seconds' if re.search(r'连续|不间断',clause) else 'observed_seconds'
        found=[]
        for label,pattern in [('person',r'行人|人群|人'),('car',r'汽车|小汽车|轿车|(?<![火单托交卡货行])车(?!辆)'),('bicycle',r'自行车|单车'),('motorcycle',r'摩托车'),('bus',r'公交车|巴士|大巴'),('truck',r'卡车|货车'),('boat',r'船')]:
            match=re.search(pattern,clause)
            if match:found.append((match.start(),{'label':label,'metric':metric}))
        for _,ranking in sorted(found,key=lambda item:item[0]):
            if ranking not in rankings:rankings.append(ranking)
    if rankings:plan['rankings']=rankings
    return plan


def appearance_duration(scene,target):
    """Sum adjacent actual sample intervals, never first-to-last across gaps."""
    fps=scene.get('sample_fps',0)
    if scene.get('kind')!='video' or type(fps) not in (int,float) or not math.isfinite(fps) or fps<=0:return None
    times=sorted({s['t'] for s in target.get('samples',[]) if type(s.get('t')) in (int,float) and math.isfinite(s['t']) and 0<=s['t']<=scene.get('duration',0)})
    if not times or any(abs(t*fps-round(t*fps))>.02 for t in times):return None
    total=longest=current=0
    for a,b in zip(times,times[1:]):
        if round(b*fps)-round(a*fps)==1:
            current+=b-a;total+=b-a;longest=max(longest,current)
        else:current=0
    return {'observed_seconds':round(total,3),'longest_interval_seconds':round(longest,3)}

def target_number(text):
    match=re.fullmatch(r'(?:目标\s*)?(\d+)\s*号?',text.strip())
    if match is None:match=re.fullmatch(r'(?:[^#\d]+\s*)?#\s*(\d+)',text.strip())
    if match is None:match=re.fullmatch(r'(?:行人|人|汽车|车辆|物体|船|公交车|卡车)\s*(\d+)\s*号?',text.strip())
    return str(int(match[1])) if match else None

def position(bbox):
    x=(bbox[0]+bbox[2])/2;y=(bbox[1]+bbox[3])/2
    column=0 if x<1/3 else 2 if x>2/3 else 1
    row=0 if y<1/3 else 2 if y>2/3 else 1
    return [['左上方','上方中部','右上方'],['左侧中部','画面中央','右侧中部'],['左下方','下方中部','右下方']][row][column]

def track_profile(scene,target):
    """No interpolated presence, physical height, actions, or gender inference."""
    if scene['kind']=='image':
        return {'trajectory':{'value':None,'text':'移动路线：这是单张图片，无法判断移动路线。','status':'insufficient'},
            'visibility':{'value':None,'text':'消失情况：这是单张图片，无法判断出现或消失的时间。','status':'insufficient'}}
    fps=scene.get('sample_fps',0);duration=scene.get('duration',0)
    samples=[]
    for sample in target.get('samples',[]):
        t=sample.get('t');bbox=sample.get('bbox',[])
        if type(t) not in (int,float) or not math.isfinite(t) or not 0<=t<=duration:continue
        if len(bbox)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in bbox):continue
        if bbox[0]>=bbox[2] or bbox[1]>=bbox[3]:continue
        samples.append({'t':t,'bbox':bbox})
    samples=sorted({s['t']:s for s in samples}.values(),key=lambda s:s['t'])
    last=target['last_seen'];tail=max(0,round(duration-last,3))
    ending=f"最后识别：{last:g}秒最后被识别到，距离视频结束还有{tail:g}秒；实际离开时刻无法确定。"
    if not samples or type(fps) not in (int,float) or not math.isfinite(fps) or fps<=0:
        return {'trajectory':{'value':None,'text':'移动路线：当前结果缺少可用的位置记录，无法还原。','status':'insufficient'},
            'visibility':{'value':{'last_seen':last,'tail_seconds':tail},'text':ending+'当前缺少逐帧记录，无法核对中途是否消失。','status':'insufficient'}}
    indices=[round(s['t']*fps) for s in samples]
    on_grid=all(abs(s['t']*fps-index)<.02 for s,index in zip(samples,indices))
    gaps=[]
    if on_grid:
        for previous,current,a,b in zip(samples,samples[1:],indices,indices[1:]):
            missing=b-a-1
            if missing>0:gaps.append({'after':previous['t'],'before':current['t'],'missing_samples':missing,'missing_sample_seconds':round(missing/fps,3)})
    missing_seconds=round(sum(g['missing_sample_seconds'] for g in gaps),3)
    if not on_grid:gap_note='采样时间不规则，无法可靠统计中途未识别的时长。'
    elif gaps:gap_note=f"中途有{len(gaps)}段没识别到，不能确定是离开、遮挡还是漏检。"
    else:gap_note='中途没有中断记录；仍不能据此证明一直可见。'
    # Require a changed grid location to persist, suppressing boundary jitter.
    run=[];pending=None;pending_count=0;persist=max(2,round(fps*.4))
    for sample in samples:
        label=position(sample['bbox'])
        if not run:run.append({'t':sample['t'],'position':label});continue
        if label==run[-1]['position']:pending=None;pending_count=0;continue
        if pending!=label:pending=label;pending_count=0
        pending_count+=1
        if pending_count>=persist:run.append({'t':sample['t'],'position':label});pending=None;pending_count=0
    ending_position=position(samples[-1]['bbox'])
    if ending_position!=run[-1]['position']:run.append({'t':samples[-1]['t'],'position':ending_position})
    if len(run)>4:run=[run[0],run[len(run)//3],run[2*len(run)//3],run[-1]]
    route=' → '.join(point['position'] for point in run)
    trajectory=f'画面中的大致路线：{route}。' if len(run)>1 else f'画面中的位置：记录主要位于{route}，无法确认明显位移。'
    if gaps or not on_grid:trajectory+='未识别时段的路线无法确认。'
    return {'trajectory':{'value':run,'text':trajectory,'status':'answered','points':run},
        'visibility':{'value':{'last_seen':last,'tail_seconds':tail,'gap_count':len(gaps) if on_grid else None,'missing_sample_seconds':missing_seconds if on_grid else None},'text':ending+gap_note,'status':'answered' if on_grid else 'insufficient','gaps_preview':gaps[:8]}}
