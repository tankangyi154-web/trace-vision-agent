from concurrent.futures import ThreadPoolExecutor
import pytest
from api.store import SQLiteStore, StoreError


def reserve(store, sid, rid, fp='same'):
    return store.reserve(sid, rid, fp, {'question':'test'}, '2026-10-31', 5, 50)


def test_replay_is_deduplicated_and_content_bound(tmp_path):
    store = SQLiteStore(tmp_path/'s.db')
    sid = store.create_session()
    assert reserve(store,sid,'r1')['created']
    assert not reserve(store,sid,'r1')['created']
    with pytest.raises(StoreError, match='request_conflict'): reserve(store,sid,'r1','changed')
    for i in range(2,6): reserve(store,sid,f'r{i}')
    with pytest.raises(StoreError, match='session_limit'): reserve(store,sid,'r6')


def test_daily_limit_is_atomic_across_instances_and_restart(tmp_path):
    path = tmp_path/'s.db'
    store = SQLiteStore(path)
    sessions = [store.create_session() for _ in range(20)]
    def run(i):
        try:
            return SQLiteStore(path).reserve(sessions[i//5],f'r{i}','x',{},'2026-10-31',5,12)['created']
        except StoreError: return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(run,range(100))) == 12
    with pytest.raises(StoreError,match='daily_limit'):
        SQLiteStore(path).reserve(sessions[-1],'last','x',{},'2026-10-31',5,12)


def test_owner_and_history_are_scoped(tmp_path):
    s=SQLiteStore(tmp_path/'s.db'); a=s.create_session(); b=s.create_session()
    reserve(s,a,'r1')
    s.finish(a,'r1',{'status':'complete','answer':'computed'},'scene:A:3','question')
    assert s.get_request(a,'r1')['answer']=='computed'
    with pytest.raises(StoreError,match='not_found'): s.get_request(b,'r1')
    assert s.history(a,'scene:A:3') == [{'role':'user','content':'question'},{'role':'assistant','content':'computed'}]
    assert s.history(a,'scene:B:3') == []
    with pytest.raises(StoreError,match='session_not_found'): reserve(s,'invented','r2')


@pytest.mark.parametrize('terminal',['complete','failed'])
def test_terminal_state_cannot_be_overwritten_by_late_tool_thread(tmp_path,terminal):
    s=SQLiteStore(tmp_path/'s.db'); sid=s.create_session()
    reserve(s,sid,'r1')
    s.update(sid,'r1',{'status':terminal,'stage':'terminal','answer':'final'})
    result=s.update(sid,'r1',{'status':'running','stage':'late tool','answer':None})
    assert result['status']==terminal
    assert result['stage']=='terminal'
    assert result['answer']=='final'
    assert s.get_request(sid,'r1')['status']==terminal
