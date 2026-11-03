from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import time
from threading import Event
from typing import Annotated, Literal
from uuid import UUID
from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from api.agent import run_agent, AgentError
from api.remote_agent import RemoteAgent
from api.catalog import ROOT, get_scene, list_scenes, get_evaluation
from api.config import Settings
from api.domain import analyze
from api.reports import report
from api.store import StoreError,SQLiteStore
from api.investigation import CASE_ID,SOURCE_SHA,baseline_facts,scene_version
from api.review_service import ReviewService,ReviewError
from api.uploads import UploadService,UploadError,validate_upload,class_choices,validate_classes
from vision.analyze_media import VIDEO_MAX_BYTES,MEDIA_LIMITS,MEDIA_WAIT_SECONDS
from api.runtime import inspect_runtime


class ChatRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    session_id: str=Field(min_length=32,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
    scene_id: str=Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    question: str=Field(min_length=1,max_length=600)
    zone_id: str=Field(min_length=1,max_length=16)
    dwell_seconds: float=Field(gt=0,le=120,allow_inf_nan=False)
    investigation_id: Literal['harbor-T001-gap'] | None=None
    review_id: UUID | None=None
    selected_target_id: str | None=Field(default=None,max_length=12,pattern=r'^\d+$')

    @field_validator('question')
    @classmethod
    def question_not_blank(cls,value):
        if not value.strip(): raise ValueError('Question cannot be blank')
        return value.strip()


class ReviewRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID


ERRORS={
    'session_not_found':(404,'会话已过期，请刷新后重新开始。'),
    'not_found':(404,'未找到这个请求。'),
    'request_conflict':(409,'这个请求编号已绑定其他内容，请创建新问题。'),
    'session_limit':(429,'本会话实时提问次数已用完，视频与报告仍可使用。'),
    'daily_limit':(429,'今日全站实时提问额度已用完，视频与报告仍可使用。'),
    'storage_unavailable':(503,'额度存储服务暂不可用，实时提问已关闭。'),
}


def fail(code,message=None,status=None):
    default_status,default_message=ERRORS.get(code,(503,'实时服务暂不可用。'))
    raise HTTPException(status_code=status or default_status,detail={'code':code,'message':message or default_message})


def normalize_result(result):
    # Redis Lua cjson re-encodes empty arrays as {}; keep the HTTP contract stable.
    for field in ('citations','rule_citations','tool_calls'):
        if result.get(field)=={}: result[field]=[]
    return result


def create_app(settings=None,store=None):
    settings=settings or Settings.load()
    store=store if store is not None else settings.store()
    upload_service=UploadService(enabled=not settings.production and isinstance(store,SQLiteStore),on_remove=store.forget_media if isinstance(store,SQLiteStore) else None)
    @asynccontextmanager
    async def lifespan(app):
        upload_service.start_cleanup()
        try:yield
        finally:upload_service.close()
    application=FastAPI(title='视频事件分析 Agent',version='0.1.0',docs_url='/api/docs',openapi_url='/api/openapi.json',lifespan=lifespan)
    review_service=ReviewService(settings.production)

    @application.exception_handler(UploadError)
    async def upload_error(request,error):
        from fastapi.responses import JSONResponse
        status=404 if error.code=='not_found' else 413 if error.code=='size' else 422 if error.code in ('format','decode','duration','dimensions','targets','segment') else 429 if error.code=='busy' else 503
        return JSONResponse(status_code=status,content={'detail':{'code':error.code,'message':str(error)}})

    def upload_owner(sid):
        if store is None:raise UploadError('disabled')
        store.remaining(sid,settings.session_limit)
        return sid

    @application.get('/api/object-classes')
    def object_classes():return {'classes':class_choices(),'max_selected':3}

    @application.get('/api/agent/connection')
    async def agent_connection(response:Response):
        from api.agent_connection import check_connection
        response.headers['Cache-Control']='no-store'
        return await check_connection(settings)

    @application.get('/api/presets')
    def prepared_examples():
        from api.presets import list_presets
        return {'presets':list_presets()}

    @application.get('/api/presets/{ident}')
    def prepared_example(ident:str):
        from api.presets import get_preset
        try:return get_preset(ident)
        except KeyError:fail('not_found','未找到这个演示案例。',404)

    @application.post('/api/presets/{ident}/open')
    def prepared_example_copy(ident:str,x_session_id:Annotated[str,Header(min_length=32,max_length=64)]):
        from api.presets import open_private_copy
        try:return open_private_copy(upload_service,ident,upload_owner(x_session_id))
        except KeyError:fail('not_found','未找到这个演示案例。',404)

    @application.post('/api/uploads')
    async def upload_file(request:Request,x_session_id:Annotated[str,Header(min_length=32,max_length=64)],
                          x_filename:Annotated[str,Header(max_length=1000)],x_file_size:Annotated[int,Header(gt=0,le=VIDEO_MAX_BYTES)],
                          x_target_classes:Annotated[str,Header(max_length=96)]='[]',x_analysis_scope:Annotated[str,Header(max_length=160)]='null'):
        from urllib.parse import unquote
        sid=upload_owner(x_session_id)
        if not upload_service.available():raise UploadError('environment')
        filename=unquote(x_filename)
        validate_upload(filename,x_file_size)
        try:classes=validate_classes(json.loads(x_target_classes))
        except (ValueError,TypeError) as e:raise UploadError('targets') from e
        try:scope=json.loads(x_analysis_scope)
        except (ValueError,TypeError) as error:raise UploadError('segment') from error
        job=upload_service.reserve(sid,filename,x_file_size,classes=classes,scope=scope)
        directory=upload_service._path(job['id']);source=directory/('source'+__import__('pathlib').Path(filename).suffix.lower())
        try:
            async def receive():
                size=0
                with source.open('wb') as output:
                    async for chunk in request.stream():
                        size+=len(chunk)
                        if size>x_file_size:raise UploadError('size')
                        output.write(chunk)
                if size!=x_file_size:raise UploadError('decode')
                validate_upload(filename,size)
            await asyncio.wait_for(receive(),timeout=MEDIA_LIMITS['upload_timeout_seconds'])
            return upload_service.start(job['id'],sid)
        except BaseException:
            upload_service.delete(job['id'],sid)
            raise

    @application.get('/api/uploads')
    def upload_records(response:Response,x_session_id:Annotated[str,Header(min_length=32,max_length=64)]):
        response.headers['Cache-Control']='no-store'
        return {'records':upload_service.records(x_session_id)}

    @application.get('/api/uploads/{ident}')
    def upload_status(ident:UUID,x_session_id:Annotated[str,Header(min_length=32,max_length=64)]):
        return upload_service.get(str(ident),x_session_id)

    @application.delete('/api/uploads/{ident}')
    def upload_delete(ident:UUID,x_session_id:Annotated[str,Header(min_length=32,max_length=64)]):
        upload_service.delete(str(ident),x_session_id)
        return {'deleted':True}

    @application.post('/api/uploads/{ident}/retry')
    def upload_retry(ident:UUID,x_session_id:Annotated[str,Header(min_length=32,max_length=64)]):
        return upload_service.retry(str(ident),x_session_id)

    @application.get('/api/uploads/{ident}/assets/{filename}')
    def upload_asset(ident:UUID,filename:str,token:str=Query(min_length=24,max_length=64)):
        path=upload_service.asset(str(ident),filename,token)
        return FileResponse(path,media_type='video/webm' if path.suffix=='.webm' else 'image/jpeg',
                            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})

    def scene_or_404(scene_id):
        try: return get_scene(scene_id)
        except KeyError: fail('scene_not_found','未找到该视频片段。',404)

    def live_required():
        if settings.reason or store is None:
            fail('not_configured',settings.reason or '实时提问未配置。',503)

    def read_request(sid,rid):
        result=normalize_result(store.get_request(sid,rid))
        timeout=settings.agent_timeout+(MEDIA_WAIT_SECONDS if result.get('media_scene_id') else 0)
        if result['status'] in ('queued','running') and time.time()-result.get('created_at',time.time())>timeout+20:
            result=normalize_result(store.update(sid,rid,{'status':'failed','stage':'执行状态未知，已停止等待',
                'error':{'code':'execution_unknown','message':'原执行未返回最终状态；为避免重复计费不会自动重发。已预留额度保留，视频与计算报告可继续使用。'}}))
        return result

    @application.exception_handler(StoreError)
    async def storage_error(request,error):
        from fastapi.responses import JSONResponse
        code=str(error); status,message=ERRORS.get(code,(503,'额度服务暂不可用。'))
        return JSONResponse(status_code=status,content={'detail':{'code':code if code in ERRORS else 'storage_unavailable','message':message}})

    @application.get('/api/health')
    def health():
        return {'status':'ok','project':'video-event-agent','runtime_instance':os.getenv('TRACE_DISTRIBUTION_INSTANCE'),'live_agent':settings.reason is None and store is not None,
                'reason':settings.reason,'mode':'production' if settings.production else 'local',
                'storage':'server' if os.getenv('TRACE_DEPLOYMENT')=='cloud' else 'local',
                'limits':{'session_questions':settings.session_limit,'daily_questions':settings.daily_limit},
                'model':settings.model,'provider':settings.provider,'version':'0.1.0',
                'capabilities':inspect_runtime(ROOT,local_allowed=upload_service.enabled)}

    @application.get('/api/scenes')
    def scenes(): return {'scenes':list_scenes()}

    @application.get('/api/scenes/{scene_id}')
    def detail(scene_id:str): return scene_or_404(scene_id)

    @application.get('/api/scenes/{scene_id}/analysis')
    def analysis(scene_id:str,zone_id:str='A',dwell_seconds:float=Query(3,gt=0,le=120,allow_inf_nan=False)):
        try: return analyze(scene_or_404(scene_id),zone_id,dwell_seconds)
        except ValueError: fail('invalid_zone','该片段没有所选区域。',422)

    @application.get('/api/evaluation')
    def evaluation(): return get_evaluation()

    @application.exception_handler(ReviewError)
    async def review_error(request,error):
        from fastapi.responses import JSONResponse
        code=str(error)
        return JSONResponse(status_code=404 if code=='not_found' else 503,
            content={'detail':{'code':code,'message':'未找到该复核请求。' if code=='not_found' else '本地视觉复核暂不可用；原始证据与计算仍保留。'}})

    @application.get('/api/investigation')
    def investigation(threshold:float=Query(5,ge=.5,le=60,allow_inf_nan=False)):
        scene=scene_or_404('harbor')
        return {'id':CASE_ID,'scene_id':'harbor','track_id':'T001','zone_id':'A','title':'这艘船，能确认连续驻留5秒吗？',
                'question':f'目标T001是否连续驻留超过{threshold:g}秒？',
                'source_version':SOURCE_SHA,'scene_version':scene_version(),'baseline':baseline_facts(scene,threshold),
                'gap':{'start':12.3,'end':13.1,'duration':.8,'frame_start':124,'frame_end':130},
                'original_url':scene['original_url'],
                'playback_url':'/media/harbor/playback.webm' if (ROOT/'web/public/media/harbor/playback.webm').is_file() else None,
                'poster_url':scene['poster_url'],'region_polygon':scene['zones'][0]['polygon'],
                'fps':scene['fps'],'duration':scene['duration'],
                'model_status':{'live_agent':settings.reason is None,'reason':settings.reason,'model':settings.model},
                'review_available':review_service.reason is None,'review_reason':review_service.reason,
                'latest_review_id':review_service.latest(),'limits':{'max_review_frames':7,'max_model_calls':3,'max_tool_calls':5}}

    @application.post('/api/investigation/reviews')
    def start_review(body:ReviewRequest): return review_service.start(str(body.request_id))

    @application.get('/api/investigation/reviews/{rid}')
    def get_review(rid:UUID,threshold:float=Query(5,ge=.5,le=60,allow_inf_nan=False)):
        return review_service.get(str(rid),threshold)

    @application.get('/review-media/{rid}/{filename}')
    def review_image(rid:UUID,filename:str):
        import re
        if not re.fullmatch(r'(original|crop|overlay)-01(24|25|26|27|28|29|30)\.jpg',filename):
            fail('not_found','未找到该复核图片。',404)
        path=review_service._path(str(rid))/filename
        if not path.is_file(): fail('not_found','未找到该复核图片。',404)
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=86400'})

    @application.get('/api/investigation/report')
    def review_report(review_id:UUID,threshold:float=Query(5,ge=.5,le=60,allow_inf_nan=False)):
        job=review_service.get(str(review_id),threshold)
        content=json.dumps({'report_kind':'actual_local_visual_review','case_id':CASE_ID,'review':job,
                            'model_execution_note':'此下载为实际算法与证据审计记录；模型执行以聊天请求记录为准。'},ensure_ascii=False,indent=2)
        return Response(content,media_type='application/json',headers={'Content-Disposition':'attachment; filename="harbor-T001-investigation.json"'})

    @application.get('/api/scenes/{scene_id}/report')
    def download(scene_id:str,request:Request,zone_id:str='A',dwell_seconds:float=Query(3,gt=0,le=120,allow_inf_nan=False),format:Literal['markdown','json','html']='markdown'):
        try: content,media=report(scene_or_404(scene_id),zone_id,dwell_seconds,format,str(request.base_url).rstrip('/'))
        except ValueError: fail('invalid_zone','该片段没有所选区域。',422)
        extension={'markdown':'md','html':'html','json':'json'}[format]
        return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{scene_id}-report.{extension}"','X-Content-Type-Options':'nosniff'})

    @application.post('/api/sessions')
    def session():
        if store is None: fail('not_configured',settings.reason,503)
        return {'session_id':store.create_session(),'remaining':settings.session_limit,'live_agent':settings.reason is None,'reason':settings.reason}

    @application.get('/api/requests/{rid}')
    def request_status(rid:UUID,x_session_id:Annotated[str,Header(min_length=32,max_length=64)]):
        if store is None: fail('not_configured',settings.reason,503)
        return read_request(x_session_id,str(rid))

    @application.post('/api/chat')
    async def chat(body:ChatRequest,x_media_owner:Annotated[str|None,Header(min_length=32,max_length=64)]=None):
        live_required()
        media=body.scene_id.startswith('upload-')
        media_owner=x_media_owner or body.session_id
        scene=upload_service.scene(body.scene_id,media_owner) if media else scene_or_404(body.scene_id)
        if body.selected_target_id is not None and (not media or not any(t['id']==body.selected_target_id for t in scene['targets'])):
            fail('invalid_case','选中的编号不属于当前素材，请重新选择。',422)
        if media and (body.investigation_id or body.review_id):fail('invalid_case','上传素材不能使用示例调查上下文。',422)
        if body.investigation_id and (body.scene_id!='harbor' or body.zone_id!='A'):
            fail('invalid_case','此调查只绑定harbor/T001/区域A。',422)
        if body.review_id and not body.investigation_id: fail('invalid_case','复核上下文必须绑定调查案例。',422)
        if body.review_id: review_service.get(str(body.review_id))
        try:
            if not media:analyze(scene,body.zone_id,body.dwell_seconds)
        except ValueError: fail('invalid_zone','该片段没有所选区域。',422)
        payload=body.model_dump(mode='json',exclude={'request_id','session_id'},exclude_none=True)
        fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        rid=str(body.request_id); sid=body.session_id
        day=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        reservation=await asyncio.to_thread(store.reserve,sid,rid,fingerprint,payload,day,settings.session_limit,settings.daily_limit)
        if not reservation['created']: return await asyncio.to_thread(read_request,sid,rid)
        scope=f'{body.scene_id}:{body.zone_id}:{body.dwell_seconds:g}'
        if body.investigation_id: scope+=f':{body.investigation_id}:{str(body.review_id) if body.review_id else "baseline"}'
        history=await asyncio.to_thread(store.history,sid,scope)
        cache_key=None
        if media:
            from api.answer_cache import answer_cache_key
            cache_key=answer_cache_key(scene,body.question,body.selected_target_id,history,settings)
            reused=await asyncio.to_thread(upload_service.cached_answer,body.scene_id,media_owner,cache_key)
            if reused:
                return normalize_result(await asyncio.to_thread(store.finish,sid,rid,{**reused,'status':'complete','stage':'已复用本机保存的回答','error':None},scope,body.question))
        effective_review_id=str(body.review_id) if body.review_id else None
        if body.investigation_id and not effective_review_id:
            for message in reversed(history):
                if message['role']!='assistant': continue
                try: memory=json.loads(message['content'])
                except (ValueError,TypeError): continue
                if isinstance(memory,dict) and memory.get('schema')=='investigation-memory-v1' and memory.get('case_id')==CASE_ID:
                    try:
                        candidate=str(UUID(memory['review_id']))
                        if review_service.get(candidate)['status']=='complete': effective_review_id=candidate; break
                    except (ValueError,KeyError,ReviewError): continue
        cancelled=Event()
        def stage(changes):
            if not cancelled.is_set(): store.update(sid,rid,changes)
        try:
            remote=None
            if not settings.api_key and settings.remote_agent_url:
                remote=RemoteAgent(settings,rid,on_stage=stage)
            result=await asyncio.wait_for(run_agent(scene,body.zone_id,body.dwell_seconds,body.question,history,settings,stage,
                    completion_transport=remote.complete if remote else None,
                    cancelled=cancelled,review_service=review_service if body.investigation_id else None,
                    review_id=effective_review_id,
                    media_context={'selected_target_id':body.selected_target_id} if media else None,
                    media_inspection=(lambda target,aspects=None:upload_service.inspect_target(body.scene_id,media_owner,target,aspects)) if media and settings.supports_images else None,
                    media_supplement=(lambda classes:upload_service.supplement(body.scene_id,media_owner,classes,stage)) if media else None),
                    timeout=settings.agent_timeout+(MEDIA_WAIT_SECONDS if media else 0))
            changes={**result,'status':'complete','stage':'已完成，证据引用已校验','error':None}
            if remote and remote.remaining is not None:changes['remaining']=min(remote.remaining,reservation['result']['remaining'])
            if media and cache_key and not result.get('connection') and not cancelled.is_set():
                try:await asyncio.to_thread(upload_service.cache_answer,body.scene_id,media_owner,cache_key,result)
                except (UploadError,OSError,ValueError):pass
        except AgentError as e:
            changes={**e.partial,'status':'failed','stage':'本次实时分析未完成','error':{'code':e.code,'message':e.message}}
        except asyncio.TimeoutError:
            changes={'status':'failed','stage':'本次分析超时','error':{'code':'agent_timeout','message':'已达到本次执行时限；不会自动重发。视频与计算报告仍可用。'}}
        except Exception:
            # Never expose credentials, provider error payloads, or internal file paths.
            changes={'status':'failed','stage':'本次实时分析中断','error':{'code':'execution_failed','message':'本次执行中断；不会自动重发，请保留请求编号查询状态。'}}
        finally:
            cancelled.set()
        return normalize_result(await asyncio.to_thread(store.finish,sid,rid,changes,scope,body.question))

    if (ROOT/'web/public/media/presets').is_dir():
        application.mount('/media/presets',StaticFiles(directory=ROOT/'web/public/media/presets'),name='prepared-media')
    if not settings.production and (ROOT/'web'/'public'/'media').is_dir():
        application.mount('/media',StaticFiles(directory=ROOT/'web'/'public'/'media'),name='media')
    return application


app=create_app()
