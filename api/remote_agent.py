"""Public gateway address plus a per-install identity, never a shared provider credential."""
from pathlib import Path
from contextvars import ContextVar
import asyncio,json,os,re,secrets,time
import threading
import httpx
from api.catalog import ROOT
from api.agent import AgentError

MESSAGES={'user_limit':'这份体验的10次问答已用完，仍可继续上传识别和查看结果。','daily_limit':'今天的问答次数已用完，请明天再试。','monthly_limit':'本月的问答次数已用完，请下月再试。','question_budget':'这次问题未能在处理次数内完成，请缩小范围后再试。'}
_identity_lock=threading.RLock()
browser_agent_identity=ContextVar('browser_agent_identity',default=None)
NETWORK_CODES={'connection_timeout','connection_failed','connection_interrupted','service_response','model_timeout','model_unavailable','service_unavailable'}

def record_connection(root,request_id,phase,kind,attempt,status=None):
    # Diagnostic metadata only: never log headers, tickets, questions, images or exception messages.
    try:
        path=Path(root)/'work/agent-connection.log';path.parent.mkdir(exist_ok=True)
        row={'at':time.time(),'request_id':request_id,'phase':phase,'kind':kind,'attempt':attempt}
        if status is not None:row['status']=status
        with _identity_lock:
            if path.exists() and path.stat().st_size>262144:path.replace(path.with_suffix('.log.1'))
            with path.open('a',encoding='utf8') as output:output.write(json.dumps(row)+'\n')
    except OSError:pass

def installation_token(root=ROOT):
    with _identity_lock:return _installation_token(root)

def _installation_token(root):
    path=Path(root)/'work/agent-identity.json';path.parent.mkdir(exist_ok=True)
    try:
        value=json.loads(path.read_text(encoding='utf8'))['token']
        if re.fullmatch(r'[A-Za-z0-9_-]{43,64}',value):return value
        raise ValueError('Invalid local identity')
    except FileNotFoundError:
        token=secrets.token_urlsafe(32)
        try:
            with path.open('x',encoding='utf8') as out:json.dump({'schema':1,'token':token},out)
            return token
        except FileExistsError:return installation_token(root)
    except (ValueError,KeyError,TypeError):raise AgentError('identity','本机体验信息无法读取，请重新解压应用到新目录。')

class RemoteAgent:
    def __init__(self,settings,request_id,*,root=ROOT,transport=None,on_stage=None):
        self.url=settings.remote_agent_url.rstrip('/');self.request_id=request_id;self.token=browser_agent_identity.get() or installation_token(root)
        self.ticket=None;self.remaining=None;self.transport=transport
        self.root=root;self.on_stage=on_stage

    async def _post(self,path,body):
        phase='reserve' if path=='/v1/questions' else 'answer'
        async with httpx.AsyncClient(timeout=httpx.Timeout(27,connect=7),transport=self.transport,follow_redirects=False) as client:
            for attempt in range(1,4):
                try:
                    response=await client.post(self.url+path,json=body,headers={'Authorization':'Bearer '+self.token})
                    # Reservation is idempotent for this installation + original request_id.
                    if phase=='reserve' and response.status_code in (502,503,504) and attempt<3:
                        record_connection(self.root,self.request_id,phase,'retryable_status',attempt,response.status_code)
                        await self._reconnect(attempt);continue
                    break
                except httpx.TransportError as error:
                    connect=isinstance(error,(httpx.ConnectError,httpx.ConnectTimeout,httpx.PoolTimeout))
                    safe=phase=='reserve' or connect
                    record_connection(self.root,self.request_id,phase,type(error).__name__,attempt)
                    if safe and attempt<3:
                        await self._reconnect(attempt);continue
                    code='connection_timeout' if isinstance(error,httpx.TimeoutException) else 'connection_failed' if connect else 'connection_interrupted'
                    message='暂时连接不上问答服务，已保留识别结果，可以重试这条问题。' if safe else '这次回答的连接中断，结果尚未确认，未自动重复发送。已有识别结果已保留。'
                    raise AgentError(code,message,{'connection':{'code':code,'message':message,'retryable':safe,'phase':phase,'attempts':attempt}}) from error
        try:
            if not response.is_success:
                record_connection(self.root,self.request_id,phase,'http_status',attempt,response.status_code)
                try:code=response.json().get('error',{}).get('code','service_unavailable')
                except (ValueError,AttributeError):code='service_unavailable'
                raise AgentError(code,MESSAGES.get(code,'这次问答暂时未能完成，请稍后再试。'),{'remaining':0} if code=='user_limit' else None)
            data=response.json()
            if not isinstance(data,dict):raise ValueError('Invalid gateway response')
            return data
        except (ValueError,OSError) as error:
            record_connection(self.root,self.request_id,phase,'invalid_response',attempt,response.status_code)
            raise AgentError('service_response','问答服务返回异常，识别结果已保留，请稍后重试。') from error

    async def _reconnect(self,attempt):
        if self.on_stage:self.on_stage({'status':'running','stage':f'连接中断，正在重新连接（{attempt}/2）'})
        await asyncio.sleep(.25*attempt)

    async def reserve(self):
        data=await self._post('/v1/questions',{'request_id':self.request_id})
        if not isinstance(data.get('ticket'),str) or not re.fullmatch('[a-f0-9]{64}',data['ticket']) or type(data.get('remaining')) is not int or not 0<=data['remaining']<=10:raise AgentError('service_unavailable','在线问答返回异常，请稍后再试。')
        self.ticket=data['ticket'];self.remaining=data['remaining']

    async def complete(self,body):
        if not self.ticket:await self.reserve()
        return await self._post('/v1/questions/'+self.ticket+'/completions',body)
