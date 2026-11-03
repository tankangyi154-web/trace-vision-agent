"""A keyless, cached reachability check. It never reserves a question or invokes a model."""
import asyncio,time
import httpx

_cache={}
_lock=asyncio.Lock()

async def check_connection(settings):
    if settings.reason:return {'available':False,'message':'暂时无法继续提问。'}
    if settings.api_key:return {'available':True,'message':'可以继续提问。','checked':False}
    url=settings.remote_agent_url
    if not url:return {'available':False,'message':'问答服务暂不可用。'}
    cached=_cache.get(url)
    if cached and time.monotonic()-cached[0]<20:return cached[1]
    async with _lock:
        cached=_cache.get(url)
        if cached and time.monotonic()-cached[0]<20:return cached[1]
        result={'available':False,'message':'在线画面分析暂未连接，数量和时长仍可查询。','checked':True}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(6,connect=4),follow_redirects=False) as client:
                response=await client.get(url.rstrip('/')+'/health')
            data=response.json()
            if response.status_code==200 and data.get('status')=='ok' and data.get('protocol')=='trace-gateway-v1':
                result={'available':True,'message':'可以继续提问。','checked':True}
        except (httpx.HTTPError,ValueError,AttributeError):pass
        _cache[url]=(time.monotonic(),result)
        return result
