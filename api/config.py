from dataclasses import dataclass,field
from pathlib import Path
import json
import os
from urllib.parse import urlsplit
from dotenv import load_dotenv
from api.catalog import ROOT
from api.store import RedisStore, SQLiteStore

load_dotenv(ROOT/'.env.local')

def shared_service():
    try:
        data=json.loads((ROOT/'data/agent-service.json').read_text(encoding='utf8'))
        url=os.getenv('TRACE_AGENT_SERVICE_URL',data['url']).rstrip('/')
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Invalid service')
        return {'url':url,'model':data['model']}
    except (OSError,ValueError,KeyError,TypeError):return {'url':'','model':'deepseek-flash'}


def bounded_int(name,default,upper):
    return max(1,min(upper,int(os.getenv(name,str(default)))))


@dataclass(frozen=True)
class Settings:
    provider: str='deepseek'
    api_key: str=field(default='',repr=False)
    base_url: str='https://api.deepseek.com'
    model: str='deepseek-flash'
    redis_url: str=''
    redis_token: str=field(default='',repr=False)
    production: bool=False
    session_limit: int=5
    daily_limit: int=50
    model_timeout: int=22
    agent_timeout: int=78
    remote_agent_url: str=''

    @classmethod
    def load(cls):
        provider=os.getenv('LLM_PROVIDER','deepseek').lower()
        if provider not in ('deepseek','qwen'): raise ValueError('LLM_PROVIDER must be deepseek or qwen')
        deepseek=provider=='deepseek'
        service=shared_service() if deepseek else {'url':'','model':'qwen-plus'}
        return cls(provider=provider,api_key=os.getenv('DEEPSEEK_API_KEY' if deepseek else 'DASHSCOPE_API_KEY',''),
                   base_url=os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com') if deepseek else os.getenv('DASHSCOPE_BASE_URL','https://dashscope.aliyuncs.com/compatible-mode/v1'),
                   model=os.getenv('LLM_MODEL',service['model']),redis_url=os.getenv('UPSTASH_REDIS_REST_URL',''),
                   remote_agent_url=service['url'],
                   redis_token=os.getenv('UPSTASH_REDIS_REST_TOKEN',''),
                   production=bool(os.getenv('VERCEL')) or os.getenv('APP_MODE')=='production',
                   session_limit=bounded_int('SESSION_QUESTION_LIMIT',10 if service['url'] else 5,100),daily_limit=bounded_int('DAILY_QUESTION_LIMIT',100 if service['url'] else 50,10000),
                   model_timeout=bounded_int('MODEL_TIMEOUT_SECONDS',22,25),agent_timeout=bounded_int('AGENT_TIMEOUT_SECONDS',78,85))

    @property
    def supports_images(self):
        return self.provider=='deepseek' and self.model in ('deepseek-flash','deepseek-v4-flash-vision-exp') or self.provider=='qwen' and self.model.startswith(('qwen-vl','qwen2-vl','qwen2.5-vl','qwen3-vl'))

    @property
    def reason(self):
        if not self.api_key and not self.remote_agent_url: return '尚未配置服务端模型密钥；视频、事件统计与报告可正常体验。'
        if self.production and not (self.redis_url and self.redis_token):
            return '线上持久化额度服务尚未配置，实时提问已关闭。'
        return None

    def store(self):
        if self.redis_url and self.redis_token: return RedisStore(self.redis_url,self.redis_token)
        if self.production: return None
        return SQLiteStore(Path(os.getenv('TRACE_LOCAL_STATE_DIR',str(ROOT/'work')))/'local.sqlite3')
