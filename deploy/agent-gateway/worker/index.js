const JSON_HEADERS={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:JSON_HEADERS})
class GatewayError extends Error {constructor(code,message,status=400){super(message);this.code=code;this.status=status}}
const fail=(code,message,status)=>{throw new GatewayError(code,message,status)}
const positive=(value,fallback,cap)=>Math.max(1,Math.min(cap,Number.parseInt(value,10)||fallback))
export function limits(env){return {daily:positive(env.DAILY_QUESTION_LIMIT,100,100),monthly:positive(env.MONTHLY_QUESTION_LIMIT,1000,1000),user:positive(env.USER_QUESTION_LIMIT,10,10),model_calls_per_question:3}}
async function hash(value){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(b=>b.toString(16).padStart(2,'0')).join('')}
async function boundedJSON(request,max){
 if(Number(request.headers.get('content-length'))>max)fail('request_size','本次提问包含的内容过多，请缩小范围。',413)
 if(!request.headers.get('content-type')?.startsWith('application/json'))fail('format','请求格式无效。',415)
 const reader=request.body?.getReader();if(!reader)fail('format','请求内容为空。')
 const chunks=[];let length=0
 while(true){const row=await reader.read();if(row.done)break;length+=row.value.byteLength;if(length>max){await reader.cancel();fail('request_size','本次提问包含的内容过多，请缩小范围。',413)}chunks.push(row.value)}
 const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length}
 try{return JSON.parse(new TextDecoder().decode(bytes))}catch{fail('format','请求内容无法读取。')}
}
export function validateCompletion(body,model){
 if(!body||typeof body!=='object'||Array.isArray(body))fail('format','提问内容无效。')
 const allowed=new Set(['model','messages','temperature','max_tokens','tools','tool_choice','thinking','enable_thinking','response_format'])
 if(Object.keys(body).some(k=>!allowed.has(k)))fail('format','提问包含不支持的选项。')
 if(body.model!==model||!Array.isArray(body.messages)||!body.messages.length||body.messages.length>50)fail('format','提问模型或上下文无效。')
 let text=0,images=0,imageBytes=0;const clean=[]
 for(const message of body.messages){
  if(!message||!['system','user','assistant','tool'].includes(message.role))fail('format','对话格式无效。')
  const content=message.content
  if(typeof content==='string')text+=content.length
  else if(Array.isArray(content)){
   for(const part of content){
    if(part?.type==='text'&&typeof part.text==='string')text+=part.text.length
    else if(part?.type==='image_url'){
     const url=part.image_url?.url
     if(typeof url!=='string'||url.length>1000000||!/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(url))fail('image_limit','只接受本次选取的有限目标截图。')
     images++;imageBytes+=url.length
    }else fail('format','不支持这类对话内容。')
   }
  }else if(content!==null&&content!==undefined)fail('format','对话内容无效。')
  const item={role:message.role,content:content??null}
  if(message.tool_calls){if(!Array.isArray(message.tool_calls)||message.tool_calls.length>5)fail('format','工具调用过多。');item.tool_calls=message.tool_calls;text+=JSON.stringify(message.tool_calls).length}
  if(message.tool_call_id){if(typeof message.tool_call_id!=='string'||message.tool_call_id.length>200)fail('format','工具编号无效。');item.tool_call_id=message.tool_call_id}
  clean.push(item)
 }
 if(text>45000||images>6||imageBytes>6000000)fail('context_limit','这次问题涉及的内容过多，请减少物体或缩短问题。',413)
 if(body.tools&&(!Array.isArray(body.tools)||body.tools.length>25||JSON.stringify(body.tools).length>40000))fail('format','工具定义过多。')
 const result={model,messages:clean,temperature:.1,max_tokens:Math.min(1800,Math.max(1,Number(body.max_tokens)||1200)),thinking:{type:'disabled'}}
 if(body.tools)result.tools=body.tools
 if(body.tool_choice==='auto'||body.tool_choice==='none')result.tool_choice=body.tool_choice
 if(body.response_format?.type==='json_object')result.response_format={type:'json_object'}
 return result
}
export function createGateway({upstream=globalThis.fetch.bind(globalThis),now=()=>Date.now()}={}){
 return {async fetch(request,env){try{
  const url=new URL(request.url),caps=limits(env),model=env.LLM_MODEL||'deepseek-flash'
  const enabled=env.GATEWAY_ENABLED!=='false'&&!!env.PROVIDER_API_KEY&&!!env.DB
  if(request.method==='GET'&&url.pathname==='/health')return json({status:enabled?'ok':'unavailable',model,limits:caps,protocol:'trace-gateway-v1'},enabled?200:503)
  if(request.method==='GET'&&url.pathname==='/')return new Response('视迹 Trace 问答服务。请从本地分析工作台提问。',{headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}})
  if(!enabled)fail('service_unavailable','问答服务暂不可用，请稍后再试。',503)
  if(request.method!=='POST')fail('not_found','未找到这个接口。',404)
  const token=request.headers.get('Authorization')?.match(/^Bearer ([A-Za-z0-9_-]{43,64})$/)?.[1]
  if(!token)fail('identity','这份体验身份无效，请重新打开应用。',401)
  const user=await hash('trace-user-v1:'+env.PROVIDER_API_KEY+':'+token),stamp=Math.floor(now()/1000)
  if(url.pathname==='/v1/questions'){
   const body=await boundedJSON(request,2048)
   if(!body||Object.keys(body).some(k=>k!=='request_id')||!/^([a-f0-9]{8}-){1}[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(body.request_id||''))fail('format','提问编号无效。')
   const id=await hash('trace-question-v1:'+user+':'+body.request_id)
   const date=new Date(now()+8*3600000).toISOString(),day='day:'+date.slice(0,10),month='month:'+date.slice(0,7)
   const statement=(sql,...args)=>env.DB.prepare(sql).bind(...args)
   await env.DB.batch([
    statement('INSERT OR IGNORE INTO gateway_users(user_key,used,created_at) VALUES(?,0,?)',user,stamp),
    statement('INSERT OR IGNORE INTO gateway_quotas(quota_key,used) VALUES(?,0)',day),
    statement('INSERT OR IGNORE INTO gateway_quotas(quota_key,used) VALUES(?,0)',month),
    statement('INSERT OR IGNORE INTO gateway_questions(id,user_key,day_key,month_key,created_at,expires_at) SELECT ?,?,?,?,?,? WHERE (SELECT used FROM gateway_users WHERE user_key=?)<? AND (SELECT used FROM gateway_quotas WHERE quota_key=?)<? AND (SELECT used FROM gateway_quotas WHERE quota_key=?)<?',id,user,day,month,stamp,stamp+900,user,caps.user,day,caps.daily,month,caps.monthly),
    statement('UPDATE gateway_users SET used=used+1 WHERE user_key=? AND EXISTS(SELECT 1 FROM gateway_questions WHERE id=? AND counted=0)',user,id),
    statement('UPDATE gateway_quotas SET used=used+1 WHERE quota_key IN (?,?) AND EXISTS(SELECT 1 FROM gateway_questions WHERE id=? AND counted=0)',day,month,id),
    statement('UPDATE gateway_questions SET counted=1 WHERE id=? AND counted=0',id),
   ])
   const question=await statement('SELECT * FROM gateway_questions WHERE id=? AND user_key=?',id,user).first()
   const identity=await statement('SELECT used FROM gateway_users WHERE user_key=?',user).first()
   if(!question){
    if(identity.used>=caps.user)fail('user_limit','这份体验的10次问答已用完，仍可继续上传识别和查看结果。',429)
    const used=await statement('SELECT used FROM gateway_quotas WHERE quota_key=?',day).first()
    fail(used.used>=caps.daily?'daily_limit':'monthly_limit',used.used>=caps.daily?'今天的问答次数已用完，请明天再试。':'本月的问答次数已用完，请下月再试。',429)
   }
   if(question.expires_at<=stamp)fail('question_expired','这次提问已过期，请发起新问题。',410)
   return json({ticket:id,remaining:Math.max(0,caps.user-identity.used),expires_at:question.expires_at,limits:caps})
  }
  const ticket=url.pathname.match(/^\/v1\/questions\/([a-f0-9]{64})\/completions$/)?.[1]
  if(!ticket)fail('not_found','未找到这个接口。',404)
  const body=validateCompletion(await boundedJSON(request,6500000),model)
  const claimed=await env.DB.prepare('UPDATE gateway_questions SET model_calls=model_calls+1 WHERE id=? AND user_key=? AND counted=1 AND expires_at>? AND model_calls<3 RETURNING model_calls').bind(ticket,user,stamp).first()
  if(!claimed)fail('question_budget','这次问题的处理次数已用完或已过期，请缩小范围后再提问。',429)
  let response
  try{response=await upstream('https://api.deepseek.com/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+env.PROVIDER_API_KEY},body:JSON.stringify(body),signal:AbortSignal.timeout(22000)})}catch(error){console.warn(JSON.stringify({event:'provider_connection_failed',timeout:['TimeoutError','AbortError'].includes(error?.name)}));fail('model_unavailable','这次回答未能完成，请稍后再试。',503)}
  if(!response.ok){let code='unknown';try{const error=(await response.json()).error;const value=String(error?.code||error?.type||'unknown');if(/^[a-zA-Z0-9_-]{1,48}$/.test(value))code=value}catch{}console.warn(JSON.stringify({event:'provider_rejected',status:response.status,code}));fail('model_unavailable','这次回答未能完成，请稍后再试。',503)}
  const answer=await response.json()
  if(!Array.isArray(answer.choices))fail('model_unavailable','这次回答未能完成，请稍后再试。',503)
  return json(Object.fromEntries(['id','model','created','choices','usage'].filter(key=>key in answer).map(key=>[key,answer[key]])))
 }catch(error){return error instanceof GatewayError?json({error:{code:error.code,message:error.message}},error.status):json({error:{code:'service_unavailable',message:'问答服务暂不可用，请稍后再试。'}},503)}}}
}
export default createGateway()
