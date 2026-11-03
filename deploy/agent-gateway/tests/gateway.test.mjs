import {DatabaseSync} from 'node:sqlite'
import {readFileSync} from 'node:fs'
import {test} from 'node:test'
import assert from 'node:assert/strict'
import {createGateway} from '../worker/index.js'
function harness(extra={}){
 const db=new DatabaseSync(':memory:');db.exec(readFileSync(new URL('../drizzle/0000_gateway.sql',import.meta.url),'utf8'))
 const prepare=sql=>({bind(...args){return {first:async()=>db.prepare(sql).get(...args)??null,run:()=>db.prepare(sql).run(...args)}}})
 const DB={prepare,batch:async statements=>{db.exec('BEGIN');try{const results=statements.map(s=>s.run());db.exec('COMMIT');return results}catch(e){db.exec('ROLLBACK');throw e}}}
 const env={DB,PROVIDER_API_KEY:'fixture-provider-secret',...extra};let calls=0,clock=Date.parse('2026-11-03T10:00:00Z')
 const handler=createGateway({now:()=>clock,upstream:async(url,options)=>{
  calls++;assert.equal(url,'https://api.deepseek.com/chat/completions');assert.equal(options.headers.Authorization,'Bearer fixture-provider-secret')
  const body=JSON.parse(options.body);assert.ok(body.max_tokens<=1800)
  return Response.json({choices:[{message:{content:'{"answer":"已核对画面"}'}}],usage:{prompt_tokens:10,completion_tokens:10},untrusted_extra:'must not return'})
 }})
 const invoke=(path,token='a'.repeat(43),body={request_id:crypto.randomUUID()})=>handler.fetch(new Request('https://example.test'+path,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:JSON.stringify(body)}),env)
 return {invoke,handler,env,db,calls:()=>calls,advance:ms=>{clock+=ms}}
}
test('one question reserves once across retries and caps model calls at three',async()=>{
 const h=harness(),request_id=crypto.randomUUID(),a=await (await h.invoke('/v1/questions',undefined,{request_id})).json()
 const b=await (await h.invoke('/v1/questions',undefined,{request_id})).json();assert.equal(a.ticket,b.ticket);assert.equal(a.remaining,9);assert.equal(b.remaining,9)
 const body={model:'deepseek-flash',messages:[{role:'user',content:'概括已提供的画面'}],max_tokens:99999}
 for(let i=0;i<3;i++){const response=await h.invoke('/v1/questions/'+a.ticket+'/completions',undefined,body);assert.equal(response.status,200);assert.ok(!JSON.stringify(await response.json()).includes('untrusted_extra'))}
 assert.equal((await h.invoke('/v1/questions/'+a.ticket+'/completions',undefined,body)).status,429)
 assert.equal(h.calls(),3);assert.equal(h.db.prepare('SELECT used FROM gateway_users').get().used,1)
})
test('personal limit survives distinct question IDs and retrying a prior question does not reset it',async()=>{
 const h=harness();for(let i=0;i<10;i++)assert.equal((await h.invoke('/v1/questions')).status,200)
 const rejected=await h.invoke('/v1/questions');assert.equal(rejected.status,429);assert.equal((await rejected.json()).error.code,'user_limit')
})
test('concurrent identities cannot overrun the global daily quota',async()=>{
 const h=harness({DAILY_QUESTION_LIMIT:'7'})
 const responses=await Promise.all(Array.from({length:20},(_,i)=>h.invoke('/v1/questions',String(i).padStart(43,'x'))))
 assert.equal(responses.filter(r=>r.status===200).length,7)
 assert.ok(h.db.prepare('SELECT used FROM gateway_quotas').all().every(r=>r.used===7))
})
test('monthly cap persists across a day boundary',async()=>{
 const h=harness({MONTHLY_QUESTION_LIMIT:'2'})
 assert.equal((await h.invoke('/v1/questions','a'.repeat(43))).status,200);h.advance(86400000)
 assert.equal((await h.invoke('/v1/questions','b'.repeat(43))).status,200)
 const response=await h.invoke('/v1/questions','c'.repeat(43));assert.equal(response.status,429);assert.equal((await response.json()).error.code,'monthly_limit')
})
test('foreign tickets, external image URLs and expired requests cannot reach the provider',async()=>{
 const h=harness(),ticket=(await (await h.invoke('/v1/questions')).json()).ticket
 const body={model:'deepseek-flash',messages:[{role:'user',content:'正常文本'}]}
 assert.equal((await h.invoke('/v1/questions/'+ticket+'/completions','b'.repeat(43),body)).status,429)
 const invalid={...body,messages:[{role:'user',content:[{type:'image_url',image_url:{url:'https://example.com/private.jpg'}}]}]}
 assert.equal((await h.invoke('/v1/questions/'+ticket+'/completions',undefined,invalid)).status,400)
 h.advance(901000);assert.equal((await h.invoke('/v1/questions/'+ticket+'/completions',undefined,body)).status,429);assert.equal(h.calls(),0)
 const health=await h.handler.fetch(new Request('https://example.test/health'),h.env);const text=await health.text();assert.ok(!text.includes('fixture-provider-secret'));assert.match(text,/1000/)
})
