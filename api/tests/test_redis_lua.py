"""Execute production Lua locally. This is not an Upstash network acceptance test."""
from concurrent.futures import ThreadPoolExecutor
import fakeredis
import pytest
from api.index import normalize_result
from api.store import RedisStore, StoreError


def make_store(redis=None):
    redis=redis or fakeredis.FakeRedis(decode_responses=True)
    store=RedisStore('https://unused.test','not-a-real-token')
    store.command=lambda *args:redis.execute_command(*args)
    return store,redis


def test_lua_owner_dedup_fingerprint_and_terminal_guard():
    s,r=make_store(); a=s.create_session(); b=s.create_session()
    first=s.reserve(a,'r1','same',{},'2026-10-31',5,50)
    assert first['created'] and first['result']['remaining']==4
    assert normalize_result(first['result'])['citations']==[]
    assert not s.reserve(a,'r1','same',{},'2026-10-31',5,50)['created']
    with pytest.raises(StoreError,match='request_conflict'): s.reserve(a,'r1','changed',{},'2026-10-31',5,50)
    with pytest.raises(StoreError,match='not_found'): s.get_request(b,'r1')
    s.update(a,'r1',{'status':'failed','stage':'terminal','error':{'code':'model_timeout','message':'test'}})
    assert s.update(a,'r1',{'status':'running','stage':'late thread'})['status']=='failed'
    assert s.get_request(a,'r1')['stage']=='terminal'
    assert r.get(s.key('day','2026-10-31'))=='1'


def test_lua_parallel_budget_survives_new_store_instances():
    s,r=make_store(); sessions=[s.create_session() for _ in range(20)]
    def run(i):
        other,_=make_store(r)
        try: return other.reserve(sessions[i//5],f'r{i}','x',{},'2026-10-31',5,12)['created']
        except StoreError: return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(run,range(100)))==12
    other,_=make_store(r)
    with pytest.raises(StoreError,match='daily_limit'):
        other.reserve(sessions[-1],'extra','x',{},'2026-10-31',5,12)


def test_lua_session_limit_expiry_and_history_scope():
    s,r=make_store(); sid=s.create_session()
    for i in range(5): s.reserve(sid,f'r{i}','x',{},'2026-10-31',5,50)
    with pytest.raises(StoreError,match='session_limit'): s.reserve(sid,'six','x',{},'2026-10-31',5,50)
    s.finish(sid,'r0',{'status':'complete','answer':'real result'},'scene:A:3','q')
    assert s.history(sid,'scene:A:3')==[{'role':'user','content':'q'},{'role':'assistant','content':'real result'}]
    assert s.history(sid,'scene:B:3')==[]
    r.delete(s.key('session',sid))
    with pytest.raises(StoreError,match='session_not_found'): s.reserve(sid,'next-day','x',{},'2026-11-01',5,50)
