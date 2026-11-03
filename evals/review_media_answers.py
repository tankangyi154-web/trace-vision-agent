"""Independent review bookkeeping. No model calls, invented labels or empty-set scores."""
import argparse
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIMENSIONS=('question_coverage','fact_accuracy','citation_alignment','unnecessary_refusal','unsupported_inference')


def final_cases(report):
    rows={row['id']:dict(row) for row in report['cases']}
    for row in report.get('rechecks',[]):rows[row['id']].update(row)
    return list(rows.values())


def review_template(report):
    return {'schema':'trace-independent-review-v1','reviewer':{'id':'','kind':'human','independent':False},
        'note':'留空表示尚未核对；pass为未发现该项问题，fail为发现问题。不得用模型自评分替代独立人工标注。',
        'cases':[{'id':r['id'],'question':r['question'],'answer':r.get('answer'),'source_sha256':r.get('source_sha256'),
            'ratings':dict.fromkeys(DIMENSIONS),'comment':''} for r in final_cases(report)]}


def summarize_review(data,expected_ids,expected_cases=None):
    if data.get('schema')!='trace-independent-review-v1':raise ValueError('未知人工核对格式')
    reviewer=data.get('reviewer',{})
    eligible=bool(str(reviewer.get('id','')).strip()) and reviewer.get('kind')=='human' and reviewer.get('independent') is True
    expected={r['id']:r for r in expected_cases} if expected_cases is not None else None
    seen=set();complete=0;metrics={k:{'pass':0,'fail':0,'not_applicable':0,'pending':0} for k in DIMENSIONS}
    for row in data.get('cases',[]):
        ident=row.get('id')
        if ident not in expected_ids or ident in seen:raise ValueError('编号缺失、重复或不属于本轮核对集')
        if expected is not None and any(row.get(k)!=expected[ident].get(k) for k in ('question','answer','source_sha256')):
            raise ValueError('评审所用素材或回答与当前核对集不一致，不能沿用旧分数')
        seen.add(ident);ratings=row.get('ratings',{})
        if set(ratings)!=set(DIMENSIONS):raise ValueError('必须逐项核对五个方面')
        for key,value in ratings.items():
            if value not in (None,'pass','fail','not_applicable'):raise ValueError('无效的核对标记')
            if key in ('question_coverage','fact_accuracy') and value=='not_applicable':raise ValueError('不能跳过问题覆盖和事实核对')
            if eligible:metrics[key]['pending' if value is None else value]+=1
        if eligible and all(v is not None for v in ratings.values()):complete+=1
    for key in DIMENSIONS:
        metrics[key]['pending']+=len(expected_ids)-len(seen) if eligible else len(expected_ids)
        denominator=metrics[key]['pass']+metrics[key]['fail']
        metrics[key]['pass_rate']=metrics[key]['pass']/denominator if denominator else None
    return {'status':'complete' if eligible and complete==len(expected_ids) and expected_ids else 'pending',
        'reviewer_identity':'self_declared_not_programmatically_verified','eligible_reviewer_declared':eligible,
        'total_cases':len(expected_ids),'reviewed_cases':complete,'metrics':metrics}


def summarize_height(data):
    if data.get('schema')!='trace-measured-height-v1':raise ValueError('未知身高核对格式')
    errors=[];interval_errors=[];covered=0;verified=0;point_count=0
    for row in data.get('cases',[]):
        if row.get('measurement_verified') is not True:continue
        height=row.get('measured_height_cm');reference=row.get('measured_reference_cm')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (height,reference)):
            raise ValueError('实测人物身高和参照尺寸必须有效')
        if not isinstance(row.get('measurement_source'),str) or len(row['measurement_source'].strip())<10:
            raise ValueError('必须记录实测来源，不能把常见尺寸假设当作实测')
        verified+=1;estimate=row.get('predicted_range_cm');point=row.get('predicted_height_cm')
        if point is not None:
            if estimate is not None or type(point) not in (int,float) or not math.isfinite(point) or point<=0:raise ValueError('点估计无效或与范围冲突')
            errors.append(abs(point-height));point_count+=1;continue
        if estimate is None:continue # A justified abstention is not an exact estimate.
        if not isinstance(estimate,list) or len(estimate)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in estimate) or not 0<estimate[0]<estimate[1]:
            raise ValueError('预测范围无效')
        error=abs(sum(estimate)/2-height);errors.append(error);interval_errors.append(error);covered+=estimate[0]<=height<=estimate[1]
    return {'status':'measured' if errors else 'pending','verified_measurements':verified,'numeric_estimates':len(errors),
        'point_estimates':point_count,'interval_estimates':len(interval_errors),'mae_cm':sum(errors)/len(errors) if errors else None,
        'midpoint_mae_cm':sum(interval_errors)/len(interval_errors) if interval_errors else None,
        'interval_coverage':covered/len(interval_errors) if interval_errors else None,
        'note':'描述性统计，不自动证明可用于测量；拒答样本单独保留，不作为零误差。'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--review',type=Path);parser.add_argument('--height',type=Path)
    parser.add_argument('--init-review',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--catalog',type=Path)
    args=parser.parse_args()
    report=json.loads((args.catalog or ROOT/'evals/media-answer-spotcheck.json').read_text(encoding='utf8'))
    template=review_template(report)
    if args.init_review:
        if args.init_review.exists():raise SystemExit('不会覆盖已有核对记录')
        args.init_review.write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding='utf8');return
    review=json.loads(args.review.read_text(encoding='utf8')) if args.review else template
    height=json.loads(args.height.read_text(encoding='utf8')) if args.height else {'schema':'trace-measured-height-v1','cases':[]}
    result={'scope':'independent_review_readiness_not_model_accuracy','model_calls':0,
        'human_review':summarize_review(review,{r['id'] for r in final_cases(report)},final_cases(report)),'measured_height':summarize_height(height)}
    result['measured_height']['method']=height.get('method','unspecified_external_measurements')
    content=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(content,encoding='utf8')
    print(content)


if __name__=='__main__':main()
