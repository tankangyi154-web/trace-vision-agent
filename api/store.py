"""Atomic reservations. SQLite is local-only; production uses Redis REST + Lua."""
from __future__ import annotations
import json
import secrets
import sqlite3
import time
from pathlib import Path
import httpx

TTL = 86400


class StoreError(Exception):
    pass


def initial_result(rid, payload, remaining):
    return {'request_id':rid,'created_at':time.time(),'status':'queued','stage':'已收到问题，正在核对素材',
            'answer':None,'citations':[],'rule_citations':[],'tool_calls':[],
            'usage':{'input_tokens':0,'output_tokens':0,'model_calls':0,'tool_calls':0},
            'remaining':remaining,'error':None,
            **({'media_scene_id':payload['scene_id']} if payload.get('scene_id','').startswith('upload-') else {})}


def history_answer(result):
    answer=result['answer'][:6000]
    if result.get('media_plan'):
        return json.dumps({'schema':'media-memory-v1','scene_id':result.get('media_scene_id'),
            'active_targets':result.get('resolved_targets',[])[:4],'answer':answer},ensure_ascii=False)
    if result.get('investigation_id')=='harbor-T001-gap' and result.get('review_id'):
        return json.dumps({'schema':'investigation-memory-v1','answer':answer,
                           'case_id':result['investigation_id'],'review_id':result['review_id'],
                           'verification':result.get('verification')},ensure_ascii=False)
    return answer


class SQLiteStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, used INTEGER NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, used INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, session TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session TEXT NOT NULL, scope TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL);
            ''')

    def connect(self):
        return sqlite3.connect(self.path,timeout=15,isolation_level=None)

    def create_session(self):
        sid=secrets.token_urlsafe(32)
        with self.connect() as c:
            c.execute('INSERT INTO sessions VALUES(?,0,?)',(sid,time.time()+TTL))
        return sid

    def remaining(self,sid,limit):
        with self.connect() as c:
            row=c.execute('SELECT used,expires FROM sessions WHERE id=?',(sid,)).fetchone()
        if row is None or row[1] < time.time(): raise StoreError('session_not_found')
        return max(0,limit-row[0])

    def reserve(self,sid,rid,fingerprint,payload,day,session_limit,daily_limit):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                session=c.execute('SELECT used,expires FROM sessions WHERE id=?',(sid,)).fetchone()
                if not session or session[1]<time.time(): raise StoreError('session_not_found')
                old=c.execute('SELECT session,fingerprint,result FROM requests WHERE id=?',(rid,)).fetchone()
                if old:
                    if old[0]!=sid: raise StoreError('not_found')
                    if old[1]!=fingerprint: raise StoreError('request_conflict')
                    c.commit()
                    return {'created':False,'result':json.loads(old[2])}
                if session[0]>=session_limit: raise StoreError('session_limit')
                used=c.execute('SELECT used FROM days WHERE day=?',(day,)).fetchone()
                if used and used[0]>=daily_limit: raise StoreError('daily_limit')
                result=initial_result(rid,payload,session_limit-session[0]-1)
                c.execute('UPDATE sessions SET used=used+1 WHERE id=?',(sid,))
                c.execute('INSERT INTO days VALUES(?,1) ON CONFLICT(day) DO UPDATE SET used=used+1',(day,))
                c.execute('INSERT INTO requests VALUES(?,?,?,?)',(rid,sid,fingerprint,json.dumps(result,ensure_ascii=False)))
                c.commit()
                return {'created':True,'result':result}
            except Exception:
                c.rollback()
                raise

    def get_request(self,sid,rid):
        with self.connect() as c:
            row=c.execute('SELECT result FROM requests WHERE id=? AND session=?',(rid,sid)).fetchone()
        if not row: raise StoreError('not_found')
        return json.loads(row[0])

    def update(self,sid,rid,changes):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT result FROM requests WHERE id=? AND session=?',(rid,sid)).fetchone()
            if not row: c.rollback(); raise StoreError('not_found')
            result=json.loads(row[0])
            if result.get('status') in ('complete','failed'):
                c.commit()
                return result
            result.update(changes)
            c.execute('UPDATE requests SET result=? WHERE id=? AND session=?',(json.dumps(result,ensure_ascii=False),rid,sid))
            c.commit()
        return result

    def finish(self,sid,rid,changes,scope,question):
        # Serialize terminal result + history with media deletion; a deleted request cannot resurrect history.
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT result FROM requests WHERE id=? AND session=?',(rid,sid)).fetchone()
            if not row:raise StoreError('not_found')
            result=json.loads(row[0])
            if result['status'] in ('complete','failed'):c.commit();return result
            result.update(changes)
            c.execute('UPDATE requests SET result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),rid))
            if result['status']=='complete':
                c.execute('INSERT INTO messages(session,scope,question,answer) VALUES(?,?,?,?)',
                          (sid,scope,question,history_answer(result)))
            c.commit()
        return result

    def history(self,sid,scope):
        with self.connect() as c:
            rows=c.execute('SELECT question,answer FROM messages WHERE session=? AND scope=? ORDER BY id DESC LIMIT 3',(sid,scope)).fetchall()
        return [m for q,a in reversed(rows) for m in [{'role':'user','content':q},{'role':'assistant','content':a}]]

    def forget_media(self,scene_id):
        from uuid import UUID
        if scene_id!='upload-'+str(UUID(scene_id.removeprefix('upload-'))):raise ValueError('Invalid upload scope')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows=c.execute('SELECT id,result FROM requests WHERE result LIKE ?',('%'+scene_id+'%',)).fetchall()
            ids=[]
            for rid,text in rows:
                result=json.loads(text)
                if result.get('media_scene_id')==scene_id or any(e.get('evidence_id','').startswith(scene_id+'-') for e in result.get('citations',[])):
                    ids.append((rid,))
            c.executemany('DELETE FROM requests WHERE id=?',ids)
            c.execute('DELETE FROM messages WHERE scope LIKE ?',(scene_id+':%',))
            c.commit()


RESERVE_LUA = '''
local s = redis.call('GET',KEYS[1])
if not s then return cjson.encode({error='session_not_found'}) end
local session = cjson.decode(s)
local r = redis.call('GET',KEYS[2])
if r then
  local old = cjson.decode(r)
  if old.session ~= ARGV[1] then return cjson.encode({error='not_found'}) end
  if old.fingerprint ~= ARGV[2] then return cjson.encode({error='request_conflict'}) end
  return cjson.encode({created=false,result=old.result})
end
if session.used >= tonumber(ARGV[3]) then return cjson.encode({error='session_limit'}) end
local daily = tonumber(redis.call('GET',KEYS[3]) or '0')
if daily >= tonumber(ARGV[4]) then return cjson.encode({error='daily_limit'}) end
local result = cjson.decode(ARGV[5])
result.remaining = tonumber(ARGV[3])-session.used-1
session.used = session.used+1
redis.call('SET',KEYS[1],cjson.encode(session),'KEEPTTL')
redis.call('INCR',KEYS[3])
redis.call('EXPIRE',KEYS[3],172800)
redis.call('SET',KEYS[2],cjson.encode({session=ARGV[1],fingerprint=ARGV[2],result=result}),'EX',172800)
return cjson.encode({created=true,result=result})
'''

UPDATE_LUA = '''
local r = redis.call('GET',KEYS[1])
if not r then return cjson.encode({error='not_found'}) end
local old = cjson.decode(r)
if old.session ~= ARGV[1] then return cjson.encode({error='not_found'}) end
if old.result.status == 'complete' or old.result.status == 'failed' then return cjson.encode(old.result) end
local changes = cjson.decode(ARGV[2])
for k,v in pairs(changes) do old.result[k]=v end
redis.call('SET',KEYS[1],cjson.encode(old),'KEEPTTL')
return cjson.encode(old.result)
'''


class RedisStore:
    prefix='video-agent:v1:'

    def __init__(self,url,token):
        self.url=url.rstrip('/')
        self.token=token

    def command(self,*args):
        # No auto retries: transport uncertainty must not issue a second model request.
        try:
            response=httpx.post(self.url,json=list(args),headers={'Authorization':f'Bearer {self.token}'},timeout=7)
            response.raise_for_status()
            body=response.json()
            if body.get('error'): raise StoreError('storage_unavailable')
            return body['result']
        except (httpx.HTTPError,ValueError,KeyError) as e:
            raise StoreError('storage_unavailable') from e

    def key(self,kind,value): return self.prefix+kind+':'+value

    def create_session(self):
        sid=secrets.token_urlsafe(32)
        self.command('SET',self.key('session',sid),json.dumps({'used':0}),'EX',TTL,'NX')
        return sid

    def remaining(self,sid,limit):
        value=self.command('GET',self.key('session',sid))
        if not value: raise StoreError('session_not_found')
        return max(0,limit-json.loads(value)['used'])

    def reserve(self,sid,rid,fingerprint,payload,day,session_limit,daily_limit):
        result=json.loads(self.command('EVAL',RESERVE_LUA,3,self.key('session',sid),self.key('request',rid),self.key('day',day),
                           sid,fingerprint,session_limit,daily_limit,json.dumps(initial_result(rid,payload,0),ensure_ascii=False)))
        if 'error' in result: raise StoreError(result['error'])
        return result

    def get_request(self,sid,rid):
        value=self.command('GET',self.key('request',rid))
        if not value: raise StoreError('not_found')
        obj=json.loads(value)
        if obj['session']!=sid: raise StoreError('not_found')
        return obj['result']

    def update(self,sid,rid,changes):
        obj=json.loads(self.command('EVAL',UPDATE_LUA,1,self.key('request',rid),sid,json.dumps(changes,ensure_ascii=False)))
        if isinstance(obj.get('error'),str): raise StoreError(obj['error'])
        return obj

    def finish(self,sid,rid,changes,scope,question):
        result=self.update(sid,rid,changes)
        if result['status']=='complete':
            key=self.key('history',sid+':'+scope)
            self.command('LPUSH',key,json.dumps({'q':question,'a':history_answer(result)},ensure_ascii=False))
            self.command('LTRIM',key,0,2)
            self.command('EXPIRE',key,TTL)
        return result

    def history(self,sid,scope):
        rows=self.command('LRANGE',self.key('history',sid+':'+scope),0,2) or []
        return [m for text in reversed(rows) for row in [json.loads(text)]
                for m in [{'role':'user','content':row['q']},{'role':'assistant','content':row['a']}]]
