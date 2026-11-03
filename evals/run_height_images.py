"""Three public image cases, at most three actual provider calls; labels stay out of inference."""
import hashlib,json,sys,time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import httpx
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/height-validation';DATA=OUT/'uw'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from api.agent import run_agent,AgentError
from api.index import create_app
from api.config import Settings
from api.store import SQLiteStore
settings=Settings.load();calls=0;request_calls=0


async def provider(messages,schemas,force):
    global calls,request_calls
    if calls>=3 or request_calls>=1:raise AgentError('height_check_budget','本次对照的真实调用预算已用完，不自动追加调用。')
    calls+=1;request_calls+=1
    # The same provider and payload shape as production; just a smaller external-check budget.
    body={'model':settings.model,'messages':messages,'temperature':.1,'max_tokens':1800,
          'tools':schemas,'tool_choice':'none' if force else 'auto'}
    if settings.provider=='deepseek':body['thinking']={'type':'disabled'}
    else:body['enable_thinking']=False
    if force:body['response_format']={'type':'json_object'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.model_timeout,connect=8)) as remote:
        response=await remote.post(settings.base_url.rstrip('/')+'/chat/completions',json=body,headers={'Authorization':f'Bearer {settings.api_key}'})
        response.raise_for_status();return response.json()


async def bounded_agent(*args,**kwargs):
    kwargs['provider']=provider
    return await run_agent(*args,**kwargs)


def main():
    global request_calls
    if '--live' not in sys.argv:
        saved=json.loads((ROOT/'evals/height-agent-results.json').read_text(encoding='utf8'))
        print(json.dumps({'mode':'saved_report_only_no_network','summary':saved['summary']}));return
    final=OUT/'agent-height-validation.json'
    if final.exists():
        print(json.dumps({'existing_result':True,'actual_model_calls':json.loads(final.read_text(encoding='utf8'))['actual_model_calls']}));return
    private=[];rows=[]
    store=SQLiteStore(OUT/'height-qa.sqlite3')
    # Actual source labels from README. Only the question/reference reaches the provider.
    labels={1:162.56,2:180.34,3:162.56}
    app=create_app(settings,store)
    # Route handlers resolve this global while handling the request, not at creation.
    with patch('api.index.run_agent',bounded_agent),TestClient(app) as client:
        for number in (1,2,3):
            path=DATA/f'height_input{number}.jpg';content=path.read_bytes();owner=store.create_session()
            response=client.post('/api/uploads',content=content,headers={'X-Session-Id':owner,'X-Filename':f'height-sample-{number}.jpg',
                'X-File-Size':str(len(content)),'X-Target-Classes':'[0]'})
            assert response.status_code==200;job=response.json();deadline=time.monotonic()+60
            while job['status'] in ('uploading','queued','running') and time.monotonic()<deadline:
                time.sleep(.25);job=client.get('/api/uploads/'+job['id'],headers={'X-Session-Id':owner}).json()
            assert job['status']=='complete' and len(job['result']['targets'])==1
            target=job['result']['targets'][0]['id']
            question=f'人 #{target}目测多高？按手中的纸张参照给粗略范围；以作者采用的美式Letter纸尺寸假设（短边21.59厘米、长边27.94厘米）比较，注意纸张横竖方向。依据不足就具体说明。'
            started=time.monotonic();request_calls=0
            response=client.post('/api/chat',json={'request_id':str(uuid4()),'session_id':owner,'scene_id':job['scene_id'],
                'zone_id':'A','dwell_seconds':3,'question':question,'selected_target_id':target},headers={'X-Media-Owner':owner})
            assert response.status_code==200;result=response.json()
            estimate=next((f.get('value',{}).get('range_cm') for f in result.get('factual_basis',[]) if f['key']==f'target{target}.height' and isinstance(f.get('value'),dict)),None)
            truth=labels[number]
            row={'id':f'UW{number}','source_image':f'docs/height_input{number}.jpg','source_sha256':hashlib.sha256(content).hexdigest(),
                'truth_basis':'author_stated_actual_height_no_measurement_protocol_published','author_height_cm':truth,
                'measurement_verified':False,'label_pairing_verified':True,'status':result['status'],'answer':result.get('answer'),
                'predicted_range_cm':estimate,'midpoint_error_cm':round(abs(sum(estimate)/2-truth),4) if estimate else None,
                'truth_within_interval':estimate[0]<=truth<=estimate[1] if estimate else None,
                'abstained':result['status']=='complete' and estimate is None,'error_code':(result.get('error') or {}).get('code'),
                'actual_model_calls':request_calls,'usage':result.get('usage'),'elapsed_seconds':round(time.monotonic()-started,2),
                'visual_frames':result.get('visual_frame_count',0),'coverage':result.get('answer_coverage',[])}
            assert calls<=3
            for citation in result.get('citations',[]):assert client.get(citation['image_url']).status_code==200
            rows.append(row);private.append({'owner':owner,'job':job,'question':question,'result':result})
            (OUT/'private-agent-height-state.json').write_text(json.dumps(private,ensure_ascii=False),encoding='utf8')
            report={'scope':'actual_agent_image_spotcheck_against_author_labels_not_measured_street_height_accuracy',
                'source':'https://github.com/seanmiles/HeightEstimator','commit':'0441d2667f99892fe3e0beb99f6a70fe97b8f755',
                'source_reference_note':'main.cpp assumes paper is 8.5 by 11 inches at the same depth as its holder; this is an assumption, not a verified measurement.',
                'protocol':'Same frozen question for all images, labels withheld from provider; real upload/detect/extract/chat/validate path.',
                'model':settings.model,'provider':settings.provider,'actual_model_calls':calls,'max_model_calls':3,
                'request_budget':'one_provider_call_per_case_no_paid_repairs_in_this_check','cases':rows}
            final.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps(row,ensure_ascii=True),flush=True)
    errors=[r['midpoint_error_cm'] for r in rows if r['midpoint_error_cm'] is not None]
    report['summary']={'total_cases':len(rows),'numeric_estimates':len(errors),'abstentions':sum(r['abstained'] for r in rows),
        'execution_failures':sum(r['status']!='complete' for r in rows),'midpoint_mae_cm':sum(errors)/len(errors) if errors else None,
        'interval_coverage':sum(r['truth_within_interval'] is True for r in rows)/len(errors) if errors else None}
    final.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
