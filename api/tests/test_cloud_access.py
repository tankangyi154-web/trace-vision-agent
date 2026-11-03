import asyncio,base64,json
import httpx,pytest
from api.remote_agent import browser_agent_identity,RemoteAgent
from api.config import Settings
from deploy.cloud import CloudAccess

PASSWORD='fixture-cloud-passphrase-123456'

async def identity_echo(scope,receive,send):
    await asyncio.sleep(0)
    token=RemoteAgent(Settings(remote_agent_url='https://example.test'),'r').token
    await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
    await send({'type':'http.response.body','body':json.dumps({'identity':token}).encode()})

def test_cloud_refuses_missing_password():
    with pytest.raises(ValueError):CloudAccess(identity_echo,'')

def test_cloud_auth_covers_application_and_health_hides_details():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=CloudAccess(identity_echo,PASSWORD)),base_url='https://trace.test') as client:
            for path in ['/','/api/health','/api/uploads','/media/presets/daylight/poster.jpg']:
                response=await client.get(path);assert response.status_code==401 and 'www-authenticate' in response.headers
            assert (await client.get('/',auth=('trace','wrong'))).status_code==401
            response=await client.get('/readyz');assert response.status_code==200 and 'identity' not in response.text
    asyncio.run(run())

def test_browser_identities_are_stable_distinct_and_context_does_not_leak():
    async def run():
        app=CloudAccess(identity_echo,PASSWORD);transport=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,base_url='https://trace.test',auth=('trace',PASSWORD)) as a,httpx.AsyncClient(transport=transport,base_url='https://trace.test',auth=('trace',PASSWORD)) as b:
            ra,rb=await asyncio.gather(a.get('/'),b.get('/'));ta=ra.json()['identity'];tb=rb.json()['identity']
            assert ta!=tb and len(ta)==len(tb)==43
            assert (await a.get('/')).json()['identity']==ta
            assert (await b.get('/')).json()['identity']==tb
            assert browser_agent_identity.get() is None
            assert 'HttpOnly' in ra.headers['set-cookie'] and 'Secure' in ra.headers['set-cookie']
            a.cookies.clear();a.cookies.set('trace_browser','forged.cookie')
            assert (await a.get('/')).json()['identity']!=ta
    asyncio.run(run())

def test_cloud_rejects_new_input_when_storage_limit_reached(tmp_path):
    records=tmp_path/'uploads';records.mkdir();(records/'existing.bin').write_bytes(b'existing')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=CloudAccess(identity_echo,PASSWORD,records=records,max_record_bytes=8)),base_url='https://trace.test',auth=('trace',PASSWORD)) as client:
            response=await client.post('/api/uploads',headers={'X-File-Size':'20'},content=b'x')
            assert response.status_code==507
    asyncio.run(run())
