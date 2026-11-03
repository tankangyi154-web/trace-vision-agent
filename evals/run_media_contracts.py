"""Reproducible checklist contracts; no provider calls or semantic accuracy score."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api.media_plan import build_plan
from api.answer_cache import implementation_version


def run():
    source=json.loads((ROOT/'evals/media-question-cases.json').read_text(encoding='utf8'))
    targets=[{'id':ident,'label':label} for ident,label in [('48','person'),('7','person'),('9','car'),('2','car')]]
    rows=[]
    for case in source['cases']:
        scene={'id':'contract-scene','kind':case.get('kind','video'),'targets':targets}
        history=[{'role':'assistant','content':json.dumps({'schema':'media-memory-v1','scene_id':scene['id'],
                 'active_targets':case['remembered']})}] if 'remembered' in case else []
        plan=build_plan(case['question'],scene,case.get('selected'),history)
        actual=[]
        for task in plan['tasks']:
            if task['kind']=='target':actual.extend(f"target:{task['target_id']}:{f}" for f in task['facets'])
            else:actual.append(f"{task['kind']}:{task['label']}:{task['metric']}")
        passed=set(actual)==set(case['expect']) and bool(plan['clarifications'])==case.get('clarify',False) and plan['needs_planning']==case.get('semantic',False)
        rows.append({'id':case['id'],'question':case['question'],'expected':case['expect'],'actual':actual,
                     'semantic_planning_requested':plan['needs_planning'],'passed':passed})
    return {'scope':'developer_authored_question_plan_contracts_not_answer_accuracy',
        'generated_at':datetime.now(timezone.utc).isoformat(),'implementation_sha256':implementation_version(),
        'model_calls':0,'human_review':'pending','total':len(rows),'passed':sum(r['passed'] for r in rows),'cases':rows}


if __name__=='__main__':
    report=run();path=ROOT/'evals/media-question-contract-results.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
    raise SystemExit(0 if report['passed']==report['total'] else 1)
