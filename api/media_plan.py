"""Question checklists scoped to an authorized upload; no arbitrary model actions."""
import json
import re
from copy import deepcopy
from api.media_profile import question_plan,VISUAL_LABELS,PATTERNS
from vision.analyze_media import class_choices

FACETS=set(PATTERNS)
ALIASES={'穿搭':'衣着','装束':'衣着','装扮':'衣着','打扮':'衣着','衣服什么样':'衣着','多久第一次露面':'什么时候出现','首次露面':'首次出现','最后露面':'最后出现','走的路线':'移动路线','去了哪里':'移动方向','忙什么':'在做什么','手上有什么':'手里拿什么','个头':'身高','壮不壮':'体型','胖不胖':'体型','什么时候不见':'最后出现'}
PRONOUN=r'他|她|它|这(?:个|位|辆|艘|只)|那(?:个|位|辆|艘|只)|选中|刚才|上面'
ALIASES.update({'服饰':'衣着','穿戴':'衣着'})


def canonical_label(value):
    if value in ('all','全部'):return 'all'
    if value in ('vehicles','车辆'):return 'vehicles'
    for choice in class_choices():
        if value in (choice['label'],choice['name'],choice['label'].replace(' ','_'),*choice['aliases']):return choice['label'].replace(' ','_')
    raise ValueError('计划中包含不支持的物体类别。')


def subjects_in_history(history,scene):
    existing={t['id']:t for t in scene['targets']}
    for message in reversed(history):
        if message.get('role')=='assistant':
            try:memory=json.loads(message.get('content',''))
            except (ValueError,TypeError):continue
            if isinstance(memory,dict) and memory.get('schema')=='media-memory-v1' and memory.get('scene_id')==scene['id']:
                return [i for i in memory.get('active_targets',[]) if isinstance(i,str) and i in existing][:4]
        elif message.get('role')=='user':
            ids=question_plan(message.get('content',''))['targets']
            if ids:return [i for i in ids if i in existing][:4]
    return []


def _plan_from_tasks(tasks,source='rules',clarifications=None):
    clarifications=list(clarifications or [])
    if len(tasks)>5:
        tasks=tasks[:5];clarifications.append('这次先核对前五项查询，其余内容可以接着问。')
    plan={'targets':[],'facets':[],'tasks':tasks,'source':source,'clarifications':clarifications}
    for task in tasks:
        if task['kind']=='target':
            if task['target_id'] not in plan['targets']:plan['targets'].append(task['target_id'])
            for facet in task['facets']:
                if facet not in plan['facets']:plan['facets'].append(facet)
        elif task['kind']=='rank':plan.setdefault('rankings',[]).append({k:task[k] for k in ('label','metric')})
        elif task['kind']=='count':plan.setdefault('counts',[]).append({k:task[k] for k in ('label','metric')})
    return plan


def build_plan(question,scene,selected_target=None,history=()):
    text=question
    for old,new in ALIASES.items():text=text.replace(old,new)
    existing={t['id']:t for t in scene['targets']}
    selected=selected_target if selected_target in existing else None
    remembered=subjects_in_history(history,scene)
    clauses=[c for c in re.split(r'[，,；;。！？!?\n]',text) if c.strip()]
    tasks=[];targets={};clarifications=[];last_ids=[];unparsed=[]
    for clause in clauses:
        if re.match(r'\s*(?:不要|不用|无需|不必|别)(?:再)?(?:说|回答|分析|看|猜|判断)?',clause):continue
        # Reference dimensions and presentation instructions supply context; they
        # must not add clothing/body/carrying questions or force a planner round.
        if re.search(r'纸张|打印纸|白纸|Letter|标尺',clause,re.I) and re.search(r'参照|尺寸|长边|短边|横|竖|假设|规格',clause) and not question_plan(clause)['facets']:
            continue
        if re.fullmatch(r'\s*(?:依据不足就具体说明|依据不足时说明原因|注意纸张横竖方向)\s*',clause):continue
        parsed=question_plan(clause)
        before=len(tasks)
        for ranking in parsed.get('rankings',[]):
            tasks.append({'kind':'rank',**ranking})
        # Colloquial ranking forms do not require a particular word order.
        if not parsed.get('rankings') and re.search(r'谁.*(?:最多|最久|最长)|(?:哪位|哪个|哪辆).*?(?:最久|最长)|镜头最多|时间最多|待得最久',clause):
            labels=[]
            if re.search(r'人|谁|哪位',clause):labels.append('person')
            if re.search(r'汽车|轿车|车辆|哪辆|车',clause):labels.append('car')
            for label in labels:tasks.append({'kind':'rank','label':label,'metric':'longest_interval_seconds' if '连续' in clause else 'observed_seconds'})
        if re.search(r'几(?:辆|个|只|艘|类)|多少(?:辆|个|只|艘|类)?|数量|数一下|数一数',clause) and not re.search(r'几秒|几号|编号',clause):
            labels=[]
            for choice in class_choices():
                if choice['name'] in clause:labels.append((clause.index(choice['name']),choice['label'].replace(' ','_')))
            if not labels and re.search(r'车',clause):labels=[(0,'car')]
            if not labels and re.search(r'物体|东西|目标',clause):labels=[(0,'all')]
            if '车辆' in clause:labels=[(0,'vehicles')]
            for _,label in sorted(labels):
                metric='categories' if re.search(r'几类|多少类',clause) else 'count' if scene['kind']=='image' or re.search(r'整段|总共|记录',clause) else 'max_simultaneous'
                tasks.append({'kind':'count','label':label,'metric':metric})
        facets=parsed['facets']
        ids=parsed['targets']
        if parsed.get('rankings') and not ids:facets=[f for f in facets if f!='presence']
        if facets:
            if not ids:ids=last_ids[:]
            if not ids and selected:ids=[selected]
            if not ids:
                candidates=remembered[:]
                if re.search(r'他|她|这位|那位',clause):candidates=[i for i in candidates if existing[i]['label']=='person']
                elif re.search(r'辆|车',clause):candidates=[i for i in candidates if existing[i]['label'] in ('car','bus','truck','motorcycle','bicycle')]
                if len(candidates)==1:ids=candidates
            if re.search(r'另一(?:辆|个|位|艘)',clause):
                anchor=(ids or ([selected] if selected else remembered))
                others=[t['id'] for t in scene['targets'] if len(anchor)==1 and anchor[0] in existing and t['label']==existing[anchor[0]]['label'] and t['id']!=anchor[0]]
                ids=others if len(others)==1 else []
            if not ids:
                clarifications.append('你指的是哪个编号？可以先在画面中选中它，再继续问。')
            for ident in ids:
                targets.setdefault(ident,[])
                for facet in facets:
                    if facet not in targets[ident]:targets[ident].append(facet)
        if parsed['targets']:last_ids=parsed['targets']
        if len(tasks)==before and not facets and not re.search(r'简(?:单|短)|只(?:要|说).*结论|不用术语|通俗|谢谢',clause):unparsed.append(clause)
    for ident,facets in targets.items():tasks.append({'kind':'target','target_id':ident,'facets':facets})
    unique=[]
    for task in tasks:
        if task not in unique:unique.append(task)
    if len(targets)>2:
        clarifications.append('这次先核对前两个编号，其他编号可以接着提问。')
        unique=[t for t in unique if t['kind']!='target' or t['target_id'] in list(targets)[:2]]
    plan=_plan_from_tasks(unique,clarifications=list(dict.fromkeys(clarifications)))
    # An unknown request gets a bounded semantic planning round, not a guessed answer.
    plan['needs_planning']=bool(unparsed) or not unique and not clarifications
    plan['context_targets']=list(dict.fromkeys(([selected] if selected else [])+remembered))
    return plan


def validate_semantic_plan(proposed,question,scene,selected_target=None,history=()):
    if not isinstance(proposed,dict) or set(proposed)-{'tasks','clarification'}:raise ValueError('问题计划只能包含tasks和clarification。')
    rows=proposed.get('tasks',[])
    if not isinstance(rows,list) or len(rows)>5:raise ValueError('问题计划最多五项。')
    allowed=set(question_plan(question)['targets'])|set(subjects_in_history(history,scene))
    if selected_target and any(t['id']==selected_target for t in scene['targets']):allowed.add(selected_target)
    baseline=build_plan(question,scene,selected_target,history)
    tasks=deepcopy(baseline['tasks'])
    for row in rows:
        if not isinstance(row,dict):raise ValueError('计划格式无效。')
        kind=row.get('kind')
        if kind=='target' and set(row)=={'kind','target_id','facets'}:
            if row['target_id'] not in allowed:raise ValueError('不能猜一个未指定或未选中的编号，请请求澄清。')
            facets=row['facets']
            if not isinstance(facets,list) or not 1<=len(facets)<=8 or any(f not in FACETS for f in facets):raise ValueError('未知的目标查询方面。')
            task={'kind':'target','target_id':row['target_id'],'facets':list(dict.fromkeys(facets))}
        elif kind in ('rank','count') and set(row)=={'kind','label','metric'}:
            metric=row['metric']
            if metric not in (('observed_seconds','longest_interval_seconds') if kind=='rank' else ('count','max_simultaneous','categories')):raise ValueError('比较或统计方式无效。')
            task={'kind':kind,'label':canonical_label(row['label']),'metric':metric}
        else:raise ValueError('问题计划包含不支持的操作。')
        if task not in tasks:tasks.append(task)
    if len({t['target_id'] for t in tasks if t['kind']=='target'})>2:raise ValueError('本次最多查看两个编号。')
    clarification=proposed.get('clarification','')
    if not isinstance(clarification,str) or len(clarification)>150:raise ValueError('澄清文字无效。')
    if not tasks and not clarification:clarification='请说明想查的物体类别或画面中的编号。'
    plan=_plan_from_tasks(tasks,'semantic',[clarification] if clarification else [])
    plan['needs_planning']=False
    return plan


def facets_for(plan,ident):
    if 'tasks' not in plan:return plan['facets']
    return list(dict.fromkeys(f for t in plan['tasks'] if t['kind']=='target' and t['target_id']==ident for f in t['facets']))


def needs_images(plan):return any(set(facets_for(plan,i))&VISUAL_LABELS.keys() for i in plan['targets'])
