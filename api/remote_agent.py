"""Public gateway address plus a per-install identity, never a shared provider credential."""
from pathlib import Path
import json,os,re,secrets
import threading
import httpx
from api.catalog import ROOT
from api.agent import AgentError

MESSAGES={'user_limit':'这份体验的10次问答已用完，仍可继续上传识别和查看结果。','daily_limit':'今天的问答次数已用完，请明天再试。','monthly_limit':'本月的问答次数已用完，请下月再试。','question_budget':'这次问题未能在处理次数内完成，请缩小范围后再试。'}
_identity_lock=threading.RLock()

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
    def __init__(self,settings,request_id,*,root=ROOT,transport=None):
        self.url=settings.remote_agent_url.rstrip('/');self.request_id=request_id;self.token=installation_token(root)
        self.ticket=None;self.remaining=None;self.transport=transport

    async def _post(self,path,body):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(27,connect=8),transport=self.transport,follow_redirects=False) as client:
                response=await client.post(self.url+path,json=body,headers={'Authorization':'Bearer '+self.token})
            if not response.is_success:
                try:code=response.json().get('error',{}).get('code','service_unavailable')
                except (ValueError,AttributeError):code='service_unavailable'
                raise AgentError(code,MESSAGES.get(code,'这次问答暂时未能完成，请稍后再试。'),{'remaining':0} if code=='user_limit' else None)
            data=response.json()
            if not isinstance(data,dict):raise ValueError('Invalid gateway response')
            return data
        except (httpx.HTTPError,ValueError,OSError) as error:
            raise AgentError('service_unavailable','在线问答暂时无法连接，识别结果仍可查看；请稍后再试。') from error

    async def reserve(self):
        data=await self._post('/v1/questions',{'request_id':self.request_id})
        if not isinstance(data.get('ticket'),str) or not re.fullmatch('[a-f0-9]{64}',data['ticket']) or type(data.get('remaining')) is not int or not 0<=data['remaining']<=10:raise AgentError('service_unavailable','在线问答返回异常，请稍后再试。')
        self.ticket=data['ticket'];self.remaining=data['remaining']

    async def complete(self,body):
        if not self.ticket:raise AgentError('service_unavailable','这次提问尚未准备完成，请稍后再试。')
        return await self._post('/v1/questions/'+self.ticket+'/completions',body)
