"""Five read-only tools, bound to the request's scene, zone, and threshold."""
from collections import Counter
import json
import math
import re
from api.catalog import get_rules
from api.domain import analyze


def tokenize(text):
    words=re.findall(r'[a-z0-9_]+|[\u4e00-\u9fff]+',text.lower())
    return [token for w in words for token in ([w] if not re.search(r'[\u4e00-\u9fff]',w) else [w[i:i+2] for i in range(max(1,len(w)-1))])]


def retrieve_rules(query: str, limit=3):
    documents=get_rules()
    tokens=[tokenize(d['title']+' '+d['text']) for d in documents]
    q=Counter(tokenize(query)); avg=sum(map(len,tokens))/len(tokens)
    scored=[]
    for doc,terms in zip(documents,tokens):
        freq=Counter(terms); score=0.
        for term in q:
            n=sum(term in t for t in tokens)
            idf=math.log(1+(len(tokens)-n+.5)/(n+.5))
            f=freq[term]
            score+=idf*f*2.5/(f+1.5*(.25+.75*len(terms)/avg)) if f else 0
        if score>0: scored.append({**doc,'score':round(score,4)})
    return sorted(scored,key=lambda d:-d['score'])[:limit]


def schema(name,description,properties,required=()):
    return {'type':'function','function':{'name':name,'description':description,
            'parameters':{'type':'object','properties':properties,'required':list(required),'additionalProperties':False}}}


TOOL_SCHEMAS=[
    schema('search_events','检索当前片段与区域的真实事件。初始已在区内不是进入。',
           {'event_type':{'type':'string','enum':['all','enter','exit','dwell','initial_presence','observation_gap']},
            'track_id':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':20}}),
    schema('get_track','获取目标在全片中的实际轨迹摘要；首次末次出现不等于区域进出时间，不推断真实速度或身份。',
           {'track_id':{'type':'string'}},['track_id']),
    schema('calculate_dwell','程序计算当前区域内各目标累计可观测驻留及连续区间，按时长排序。',
           {'track_id':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':20}}),
    schema('get_evidence','按证据ID取得真实截图信息及截图时间。',
           {'evidence_id':{'type':'string'}},['evidence_id']),
    schema('retrieve_rules','BM25检索项目内示例区域规则和结论限制，返回规则ID。',
           {'query':{'type':'string','maxLength':200}},['query']),
]


class Toolset:
    def __init__(self,scene,zone_id,dwell_seconds):
        self.scene=scene
        self.analysis=analyze(scene,zone_id,dwell_seconds)
        self.allowed_evidence=set()
        self.allowed_rules={}

    def execute(self,name,args):
        spec=next((s['function']['parameters'] for s in TOOL_SCHEMAS if s['function']['name']==name),None)
        if spec is None: raise ValueError('Unknown tool')
        if not isinstance(args,dict) or set(args)-set(spec['properties']): raise ValueError('Unknown parameters')
        if any(k not in args for k in spec['required']): raise ValueError('Missing required parameter')
        for k,v in args.items():
            p=spec['properties'][k]
            if p['type']=='string' and (not isinstance(v,str) or len(v)>p.get('maxLength',100)):
                raise ValueError('Invalid string parameter')
            if 'enum' in p and v not in p['enum']: raise ValueError('Invalid event type')
            if p['type']=='integer' and (type(v) is not int or not p['minimum']<=v<=p['maximum']):
                raise ValueError('Invalid integer parameter')
        limit=args.get('limit',12)
        if name=='search_events':
            rows=[e for e in self.analysis['events'] if args.get('event_type','all') in ('all',e['type']) and (not args.get('track_id') or args['track_id']==e['track_id'])]
            result={'total':len(rows),'events':rows[:limit],'summary':self.analysis['summary']}
        elif name=='calculate_dwell':
            rows=[d for d in self.analysis['dwell'] if not args.get('track_id') or d['track_id']==args['track_id']]
            result={'total':len(rows),'ranking':rows[:limit],'unit':'seconds','method':'observed_only','threshold_seconds':self.analysis['dwell_seconds']}
        elif name=='get_track':
            track=next((t for t in self.scene['tracks'] if t['id']==args['track_id']),None)
            if not track: raise ValueError('Track not found in this clip')
            samples=track['samples']; step=max(1,math.ceil(len(samples)/32))
            result={'scope':'whole_clip_track','track_id':track['id'],'label':track['label'],'first_seen':samples[0]['t'],'last_seen':samples[-1]['t'],
                    'observations':len(samples),'samples':samples[::step][:32],
                    'evidence_ids':[e['id'] for e in self.scene['evidence'] if e['track_id']==track['id']][:4]}
        elif name=='get_evidence':
            result=next((e for e in self.scene['evidence'] if e['id']==args['evidence_id']),None)
            if result is None: raise ValueError('Evidence not found in this clip')
        else:
            rows=retrieve_rules(args['query'])
            self.allowed_rules.update({r['id']:r for r in rows})
            result={'rules':rows}
        if len(json.dumps(result,ensure_ascii=False))>16000:
            return {'error':'结果超过上下文预算，请用单一track_id缩小范围。'}
        self._collect(result)
        return result

    def _collect(self,obj):
        if isinstance(obj,dict):
            self.allowed_evidence.update(obj.get('evidence_ids',[]))
            if 'image_url' in obj and 'id' in obj: self.allowed_evidence.add(obj['id'])
            for value in obj.values(): self._collect(value)
        elif isinstance(obj,list):
            for value in obj: self._collect(value)

    def validate_answer(self,obj):
        if not isinstance(obj,dict) or not isinstance(obj.get('answer'),str) or not 0<len(obj['answer'])<=6000:
            raise ValueError('Model answer is not valid structured JSON')
        ids=obj.get('evidence_ids',[]); rules=obj.get('rule_ids',[])
        if not isinstance(ids,list) or any(not isinstance(i,str) or i not in self.allowed_evidence for i in ids):
            raise ValueError('Model cited evidence it did not retrieve')
        if not isinstance(rules,list) or any(not isinstance(i,str) or i not in self.allowed_rules for i in rules):
            raise ValueError('Model cited a rule it did not retrieve')
        if not ids and obj.get('insufficient_evidence') is not True:
            raise ValueError('Analytical answers must cite retrieved video evidence')
        by_id={e['id']:e for e in self.scene['evidence']}
        citations=[{'evidence_id':i,'track_id':by_id[i]['track_id'],'t':by_id[i]['t'],'image_url':by_id[i]['image_url']} for i in dict.fromkeys(ids)]
        return {'answer':obj['answer'],'citations':citations,'rule_citations':[self.allowed_rules[i] for i in dict.fromkeys(rules)],
                'insufficient_evidence':obj.get('insufficient_evidence') is True}
