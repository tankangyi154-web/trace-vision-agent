"""Invite-only cloud wrapper. TLS is supplied by Caddy, identity stays per browser."""
import base64,hashlib,hmac,os,re,secrets,shutil
from http.cookies import SimpleCookie
from pathlib import Path
from api.remote_agent import browser_agent_identity

class CloudAccess:
    def __init__(self,application,password,*,records=None,max_record_bytes=4*1024**3):
        if len(password)<20:raise ValueError('TRACE_WEB_PASSWORD must contain at least 20 characters')
        self.application=application;self.password=password.encode();self.records=records
        self.max_record_bytes=max_record_bytes

    def signed(self,token):
        return token+'.'+hmac.new(self.password,token.encode(),hashlib.sha256).hexdigest()

    def identity(self,headers):
        try:
            cookie=SimpleCookie();cookie.load(headers.get(b'cookie',b'').decode('ascii'))
            value=cookie['trace_browser'].value;token,signature=value.split('.')
            if re.fullmatch(r'[A-Za-z0-9_-]{43}',token) and hmac.compare_digest(value,self.signed(token)):return token,False
        except (KeyError,ValueError,UnicodeError):pass
        return secrets.token_urlsafe(32),True

    async def respond(self,send,status,text,headers=()):
        await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'text/plain; charset=utf-8'),(b'cache-control',b'no-store'),*headers]})
        await send({'type':'http.response.body','body':text.encode('utf8')})

    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':return await self.application(scope,receive,send)
        if scope['type']!='http':return
        headers=dict(scope.get('headers',[]))
        if scope['path']=='/readyz':return await self.respond(send,200,'Trace cloud process is running')
        expected=b'Basic '+base64.b64encode(b'trace:'+self.password)
        if not hmac.compare_digest(headers.get(b'authorization',b''),expected):
            return await self.respond(send,401,'请输入分享者提供的访问口令。',[(b'www-authenticate',b'Basic realm="Trace", charset="UTF-8"')])
        token,new=self.identity(headers)
        # Small invite-only deployment: cap outstanding input storage before accepting new media.
        if scope['path']=='/api/uploads' and scope['method']=='POST' and self.records:
            total=sum(p.stat().st_size for p in self.records.rglob('*') if p.is_file()) if self.records.exists() else 0
            try:size=int(headers.get(b'x-file-size',b'0'))
            except ValueError:size=0
            if total+max(size,0)>self.max_record_bytes or shutil.disk_usage(self.records.parent).free<max(size,0)+1024**3:
                return await self.respond(send,507,'服务器暂存空间不足，请删除旧记录或稍后再试。')
        marker=browser_agent_identity.set(base64.urlsafe_b64encode(hmac.new(self.password,token.encode(),hashlib.sha256).digest()).decode().rstrip('='))
        async def wrapped_send(message):
            if message['type']=='http.response.start':
                message=dict(message);message['headers']=list(message.get('headers',[]))
                message['headers'].append((b'cache-control',b'no-store'))
                if new:message['headers'].append((b'set-cookie',('trace_browser='+self.signed(token)+'; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Strict').encode()))
            await send(message)
        try:await self.application(scope,receive,wrapped_send)
        finally:browser_agent_identity.reset(marker)

def create_cloud_app():
    password=os.environ.get('TRACE_WEB_PASSWORD','')
    if len(password)<20:raise RuntimeError('Set a private TRACE_WEB_PASSWORD of at least 20 characters before deployment')
    os.environ['APP_MODE']='local';os.environ['TRACE_DEPLOYMENT']='cloud'
    from app import app
    from api.catalog import ROOT
    return CloudAccess(app,password,records=ROOT/'work/uploads')
