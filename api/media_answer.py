"""Compact presentation of validated facts; explanations and evidence stay available."""
import re

PROMPT_VERSION='media-answer-v4-ai-reviewed'


def distinct_descriptions(phrases):
    """Remove only repeated affirmative clauses; keep each caveat and full audit."""
    seen=set();short=[]
    for phrase in phrases:
        kept=[]
        for clause in re.split(r'[，、]',phrase):
            repeatable=4<=len(clause)<=24 and not re.search(r'不|未|无|没|难|模糊|太小|遮|参照|可能|似乎|仅',clause)
            if repeatable and clause in seen:continue
            kept.append(clause)
            if repeatable:seen.add(clause)
        if kept:short.append('，'.join(kept))
    return list(dict.fromkeys(short))


def present_answer(result,scene,plan):
    facts=result.get('factual_basis',[])
    if not facts:return result
    full=result['answer'];parts=[];groups={};rankings=[];other=[]
    by_id={t['id']:t for t in scene['targets']}
    rows={(r['target_id'],r['aspect']):r for r in result.get('visual_observations',[])}
    coverage=result.get('answer_coverage',[])
    for fact in facts:
        key=fact['key'];text=fact['text'];subject=None
        match=re.match(r'target(\d+)\.(\w+)',key)
        status=next((c['status'] for c in coverage if match and c.get('target')==match[1] and c['aspect']==('presence' if match[2]=='first_seen' else match[2])),'answered')
        if key.startswith('ranking.'):
            _,label,metric=key.split('.',2)
            status=next((c['status'] for c in coverage if c.get('scope')=='ranking' and c.get('label')==label and c['aspect']==metric),'insufficient')
        elif not match:
            status=next((c['status'] for c in coverage if c.get('scope')=='count' and key==f"{c['label']}.{c['aspect']}"),status)
        if key.endswith('.visual_review') or key.startswith('scope.'):status='insufficient'
        if key.startswith('ranking.'):
            rank=re.search(r"(?:并列)?出现最久的是(.+?)，(?:可确认的累计出现时间|连续识别时间)([\d.]+)秒",text)
            if rank:
                prefix='连续' if key.endswith('.longest_interval_seconds') else '累计'
                brief=f'{rank[1]}（{prefix}{rank[2]}秒）';rankings.append(brief)
            else:brief=text
        elif match:
            ident,aspect=match.groups();subject=ident
            text=re.sub(r'^.*? · ','',text)
            if aspect in ('gender','body','height','appearance','clothing','action','carrying'):
                row=rows.get((ident,aspect));brief=text
                if row:
                    if aspect=='height' and row.get('height_estimate'):brief=text
                    elif aspect=='height' and row['status']=='insufficient':
                        reason=row.get('reason','')+row['description']
                        cause='缺少可靠尺寸参照' if re.search(r'参照|远近|距离',reason) else '头脚没有完整出现' if re.search(r'脚|出画|截',reason) else '画面依据不足'
                        brief=f'身高{cause}，暂不能估计'
                    else:brief=row['description'].strip().rstrip('。')
                    if aspect=='carrying' and row['status']=='uncertain' and re.search(r'未见|没有|没拿|空手|未持',brief):
                        reason=row.get('reason','').strip().rstrip('。')
                        if reason and reason not in brief:brief+='（'+reason+'）'
                if status=='uncertain' and aspect=='body' and not re.search(r'看起来|目测|大致|似乎|可能',brief):brief='看起来'+brief
            else:
                brief=re.sub(r'^(?:出现时间|画面中的大致路线|画面中的位置|最后识别)：','',text).strip()
            groups.setdefault(ident,[]).append(brief.rstrip('。'))
        else:brief=text;other.append(brief)
        citations=[c['evidence_id'] for c in result.get('citations',[]) if subject and c.get('track_id')==subject]
        if key.startswith('ranking.'):
            citations=[c['evidence_id'] for c in result.get('citations',[]) if c.get('track_id') and f"#{c['track_id']}" in text.replace(' ','')]
        parts.append({'key':key,'text':brief,'details':text,'subject_id':subject,'status':'insufficient' if status in ('insufficient','unavailable') else 'interpretation' if fact.get('source')=='visual_model' else 'confirmed',
            'evidence_ids':citations})
    sentences=[]
    if rankings:sentences.append('出现最久：'+'，'.join(rankings)+'。')
    sentences.extend(other)
    for ident,phrases in groups.items():
        sentences.append(by_id.get(ident,{}).get('name',f'#{ident}')+'：'+'；'.join(distinct_descriptions(phrases))+'。')
    # Any non-ranked explanation (e.g. unavailable samples) must remain visible.
    for part in parts:
        if part['key'].startswith('ranking.') and not re.search(r'（(?:累计|连续)[\d.]+秒）',part['text']):sentences.insert(0,part['text'])
    return {**result,'answer':'\n\n'.join(sentences) or full,'answer_details':full,'answer_parts':parts,
        'answer_state':'partial' if any(p['status']=='insufficient' for p in parts) else 'answered',
        'resolved_targets':list(dict.fromkeys(plan['targets'] or [c.get('track_id') for c in result.get('citations',[]) if c.get('track_id')])),
        'media_plan':{'source':plan.get('source','rules'),'tasks':plan.get('tasks',[]),'clarifications':plan.get('clarifications',[])}}
