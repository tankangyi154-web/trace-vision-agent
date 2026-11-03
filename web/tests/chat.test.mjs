import assert from 'node:assert/strict'
import { test, beforeEach, afterEach } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { effectScope, nextTick, ref } from 'vue'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/composables/useChat.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', packages: 'external', write: false })
await writeFile(new URL('useChat.mjs', cache), bundle.outputFiles[0].text)
const { useChat } = await import(new URL('useChat.mjs', cache))
class MemoryStorage {
  values = new Map()
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, String(value)) }
  removeItem(key) { this.values.delete(key) }
}
const originalFetch = globalThis.fetch
const scopes = []
beforeEach(() => { globalThis.localStorage = new MemoryStorage(); globalThis.sessionStorage = new MemoryStorage() })
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); globalThis.fetch = originalFetch })
const health = () => ref({ live_agent: true, limits: { session_questions: 5, daily_questions: 50 }, model: 'test' })
const context = (id = 'harbor') => ref({ scene_id: id, zone_id: 'A', dwell_seconds: 3 })
function chat(ctx = context()) { const scope = effectScope(); scopes.push(scope); return scope.run(() => useChat(health(), ctx)) }
function response(body, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }) }
function complete(id) { return { request_id: id, status: 'complete', stage: 'complete', answer: '目标 T001 已进入区域。', citations: [], rule_citations: [], tool_calls: [], usage: { input_tokens: 10, output_tokens: 5, model_calls: 1, tool_calls: 0 }, remaining: 4, error: null } }
function savedPending() { return [...sessionStorage.values.values()].map(value => JSON.parse(value)).find(value => value.pending)?.pending }

test('selected target accompanies a question without splitting material history or clearing the draft', async () => {
  const ctx=context('upload-one');const state=chat(ctx);let sent
  state.question.value='他穿什么？'
  ctx.value={...ctx.value,selected_target_id:'48'};await nextTick()
  assert.equal(state.question.value,'他穿什么？')
  globalThis.fetch=async (url,init)=>{if(url==='/api/sessions')return response({session_id:'target-session',remaining:5});sent=JSON.parse(init.body);return response(complete(sent.request_id))}
  await state.send();assert.equal(sent.selected_target_id,'48')
  ctx.value={...ctx.value,selected_target_id:'7'};await nextTick()
  assert.equal(state.messages.value.length,1)
})

test('a restored record uses its owner credential while preserving the current question session and quota', async () => {
  const current = 'current-question-session'.padEnd(40, 'x'), owner = 'saved-record-owner'.padEnd(40, 'y')
  localStorage.setItem('trace-session-v1', current)
  const ctx = context('upload-11111111-1111-4111-8111-111111111111')
  const scope = effectScope(); scopes.push(scope)
  const state = scope.run(() => useChat(health(), ctx, owner))
  let posts = 0
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/chat')
    const body = JSON.parse(init.body)
    assert.equal(body.session_id, current)
    assert.equal(init.headers['X-Media-Owner'], owner)
    posts++
    return response(complete(body.request_id))
  }
  await state.send('它什么时候出现？')
  assert.equal(posts, 1)
  assert.equal(state.remaining.value, 4)
})

test('an expired upload is a terminal rejection, so it cannot lock new analysis behind a pending request', async () => {
  globalThis.fetch = async url => url === '/api/sessions' ? response({ session_id: 'expired-media-session', remaining: 5 }) : response({ detail: { code: 'not_found', message: '这份分析已删除或过期，请重新上传。' } }, 404)
  const state = chat(context('upload-11111111-1111-4111-8111-111111111111'))
  await state.send('有几辆车？')
  assert.equal(state.pending.value, null)
  assert.equal(state.canRetry.value, false)
})

test('forgetting an upload clears its cached answers but keeps another material conversation', async () => {
  let rid
  globalThis.fetch = async (url, init) => { if (url === '/api/sessions') return response({ session_id: 'forget-media-session', remaining: 5 }); rid = JSON.parse(init.body).request_id; return response(complete(rid)) }
  const ctx = context('upload-one'); const state = chat(ctx)
  await state.send('第一份')
  ctx.value = { ...ctx.value, scene_id: 'upload-two' }; await state.send('第二份')
  state.forgetScene('upload-one')
  assert.equal(state.messages.value[0].question, '第二份')
  ctx.value = { ...ctx.value, scene_id: 'upload-one' }
  assert.equal(state.messages.value.length, 0)
  assert.equal(JSON.stringify([...sessionStorage.values.values()]).includes('第一份'), false)
})

test('unknown transport outcome survives remount; reconnect queries original id with session header and does not create a new question', async () => {
  let sent
  globalThis.fetch = async (url, init) => {
    if (url === '/api/sessions') return response({ session_id: 'session-one', remaining: 5, live_agent: true })
    sent = JSON.parse(init.body)
    throw new TypeError('connection interrupted')
  }
  const first = chat()
  await first.send('谁进入了区域 A？')
  assert.deepEqual(savedPending(), sent)
  assert.equal(first.canAsk.value, false, 'an unresolved request must block a fresh question')
  scopes[0].stop()
  const restored = chat()
  assert.equal(restored.pending.value.request_id, sent.request_id)
  assert.equal(restored.messages.value[0].question, sent.question)
  const calls = []
  globalThis.fetch = async (url, init) => { calls.push([url, init]); return response(complete(sent.request_id)) }
  await restored.reconnect()
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], `/api/requests/${sent.request_id}`)
  assert.equal(calls[0][1].headers['X-Session-ID'], 'session-one')
  assert.equal(restored.pending.value, null)
  assert.equal(restored.messages.value[0].result.answer, complete(sent.request_id).answer)
  assert.equal(restored.remaining.value, 4)
  assert.equal(restored.canAsk.value, true)
})

test('404 reconnect resubmits the exact persisted payload and request id only once', async () => {
  let sent
  globalThis.fetch = async (url, init) => { if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 }); sent = JSON.parse(init.body); throw new TypeError('lost') }
  const first = chat(); await first.send('生成报告'); scopes[0].stop()
  const restored = chat(); const posts = []
  globalThis.fetch = async (url, init) => { if (url.startsWith('/api/requests/')) return response({ detail: { code: 'not_found', message: 'unknown' } }, 404); posts.push(JSON.parse(init.body)); return response(complete(sent.request_id)) }
  await restored.reconnect()
  assert.deepEqual(posts, [sent])
})

test('switching context while a request is in flight never writes its result into the new scope; completed scope is restored later', async () => {
  let finish
  let sent
  globalThis.fetch = async (url, init) => { if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 }); sent = JSON.parse(init.body); return new Promise(resolve => { finish = () => resolve(response(complete(sent.request_id))) }) }
  const ctx = context(); const state = chat(ctx)
  const running = state.send('谁进入了区域？')
  await new Promise(resolve => setTimeout(resolve, 0))
  ctx.value = { scene_id: 'night', zone_id: 'B', dwell_seconds: 4 }; await nextTick()
  assert.equal(state.messages.value.length, 0)
  assert.equal(state.canAsk.value, false)
  finish(); await running
  assert.equal(state.messages.value.length, 0)
  ctx.value = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3 }; await nextTick()
  assert.equal(state.messages.value.length, 1)
  assert.equal(state.messages.value[0].result.status, 'complete')
  scopes[0].stop()
  const restored = chat(context())
  assert.equal(restored.messages.value[0].result.status, 'complete')
})

test('restoring a pending request from another scope keeps that history separate and prevents a new model request', async () => {
  let sent
  globalThis.fetch = async (url, init) => { if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 }); sent = JSON.parse(init.body); throw new TypeError('lost') }
  const first = chat(); await first.send('谁进入区域？'); scopes[0].stop()
  const ctx = context('night'); const restored = chat(ctx)
  assert.equal(restored.pending.value.request_id, sent.request_id)
  assert.equal(restored.messages.value.length, 0)
  assert.equal(restored.canAsk.value, false)
  let requests = 0
  globalThis.fetch = async () => { requests++; return response(complete(sent.request_id)) }
  await restored.send('另一个问题')
  assert.equal(requests, 0)
  await restored.reconnect()
  assert.equal(restored.messages.value.length, 0)
  ctx.value = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3 }; await nextTick()
  assert.equal(restored.messages.value[0].result.status, 'complete')
})

test('storage failure after a model request keeps its id pending rather than permitting another charge', async () => {
  let sent
  globalThis.fetch = async (url, init) => {
    if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 })
    sent = JSON.parse(init.body)
    return response({ detail: { code: 'storage_unavailable', message: 'request result could not be saved' } }, 503)
  }
  const state = chat(); await state.send('生成报告')
  assert.equal(state.pending.value.request_id, sent.request_id)
  assert.equal(state.canAsk.value, false)
  assert.equal(savedPending().request_id, sent.request_id)
})

test('an expired restored session clears its pending lock without automatically sending a new paid request', async () => {
  let original
  globalThis.fetch = async (url, init) => { if (url === '/api/sessions') return response({ session_id: 'expired', remaining: 5 }); original = JSON.parse(init.body); throw new TypeError('lost') }
  const first = chat(); await first.send('原问题'); scopes[0].stop()
  const ctx = context('night'); const restored = chat(ctx)
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push([url, init])
    if (url.startsWith('/api/requests/')) return response({ detail: { code: 'not_found', message: 'request expired' } }, 404)
    return response({ detail: { code: 'session_not_found', message: 'session expired' } }, 404)
  }
  await restored.reconnect()
  assert.equal(calls.length, 2, 'recovery may only query/replay the original request')
  assert.deepEqual(JSON.parse(calls[1][1].body), original)
  assert.equal(restored.pending.value, null)
  assert.equal(localStorage.getItem('trace-session-v1'), null)
  assert.equal(savedPending(), undefined)
  assert.equal(restored.canAsk.value, true)
  assert.match(restored.connectionError.value, /原请求无法恢复.*会话已过期/)
  assert.equal(restored.messages.value.length, 0, 'expired request error stays out of the new scene')
  ctx.value = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3 }; await nextTick()
  assert.match(restored.messages.value[0].error, /会话已过期/)
  const nextCalls = []
  globalThis.fetch = async (url, init) => {
    nextCalls.push([url, init])
    if (url === '/api/sessions') return response({ session_id: 'new-session', remaining: 5 })
    const request = JSON.parse(init.body); return response(complete(request.request_id))
  }
  await restored.send('明确提交的新问题')
  assert.equal(nextCalls.length, 2)
  const nextRequest = JSON.parse(nextCalls[1][1].body)
  assert.equal(nextRequest.session_id, 'new-session')
  assert.notEqual(nextRequest.request_id, original.request_id)
  assert.equal(nextRequest.question, '明确提交的新问题')
})

for (const mode of ['send', 'reconnect']) {
  test(`scene_not_found during ${mode} preserves the valid session instead of treating all HTTP 404s as session expiry`, async () => {
    let firstRequest
    globalThis.fetch = async (url, init) => {
      if (url === '/api/sessions') return response({ session_id: 'valid-session', remaining: 5 })
      firstRequest = JSON.parse(init.body)
      if (mode === 'reconnect') throw new TypeError('lost')
      return response({ detail: { code: 'scene_not_found', message: 'scene removed' } }, 404)
    }
    const first = chat(); await first.send('查看场景')
    let state = first
    if (mode === 'reconnect') {
      scopes[0].stop(); state = chat()
      globalThis.fetch = async (url, init) => url.startsWith('/api/requests/')
        ? response({ detail: { code: 'not_found', message: 'unknown request' } }, 404)
        : response({ detail: { code: 'scene_not_found', message: 'scene removed' } }, 404)
      await state.reconnect()
    }
    assert.equal(localStorage.getItem('trace-session-v1'), 'valid-session')
    assert.equal(state.pending.value, null)
    assert.equal(state.canAsk.value, true)
    assert.equal(state.remaining.value, 5)
    assert.equal(state.messages.value[0].id, firstRequest.request_id)
    assert.equal(state.messages.value[0].error, 'scene removed')
  })
}

const flush = () => new Promise(resolve => setImmediate(resolve))
test('investigation and review context are sent to the API and isolate history from the legacy workbench', async () => {
  const sent = []
  globalThis.fetch = async (url, init) => {
    if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 })
    const request = JSON.parse(init.body); sent.push(request); return response(complete(request.request_id))
  }
  const ctx = context(); const current = chat(ctx)
  await current.send('旧工作台问题')
  assert.equal(sent[0].investigation_id, undefined)
  ctx.value = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3, investigation_id: 'harbor-T001-gap', review_id: 'review-one' }; await nextTick()
  assert.equal(current.messages.value.length, 0)
  await current.send('基于本次复核追问')
  assert.equal(sent[1].investigation_id, 'harbor-T001-gap')
  assert.equal(sent[1].review_id, 'review-one')
  ctx.value = { ...ctx.value, review_id: 'review-two' }; await nextTick()
  assert.equal(current.messages.value.length, 0)
  ctx.value = { ...ctx.value, review_id: 'review-one' }; await nextTick()
  assert.equal(current.messages.value[0].question, '基于本次复核追问')
  ctx.value = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3 }; await nextTick()
  assert.equal(current.messages.value[0].question, '旧工作台问题')
})

test('refreshing an equivalent evidence context preserves the next question; only an actual scope change clears it', async () => {
  const ctx = context()
  ctx.value = { ...ctx.value, investigation_id: 'harbor-T001-gap', review_id: null }
  const current = chat(ctx)
  current.question.value = '接着排除未决帧再比较'
  ctx.value = { ...ctx.value }; await nextTick()
  assert.equal(current.question.value, '接着排除未决帧再比较')
  ctx.value = { ...ctx.value, dwell_seconds: 5 }; await nextTick()
  assert.equal(current.question.value, '')
  current.question.value = '基于新复核追问'
  ctx.value = { ...ctx.value, review_id: 'explicit-review' }; await nextTick()
  assert.equal(current.question.value, '')
})

test('a delayed chat POST shows real running tool status through read-only polling and never posts twice', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let finishPost
  let request
  let posts = 0
  let reads = 0
  globalThis.fetch = async (url, init) => {
    if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 })
    if (url === '/api/chat') { posts++; request = JSON.parse(init.body); return new Promise(resolve => { finishPost = () => resolve(response(complete(request.request_id))) }) }
    reads++
    assert.equal(init.headers['X-Session-ID'], 's')
    if (reads === 1) return response({ detail: { code: 'not_found', message: 'not yet reserved' } }, 404)
    return response({ ...complete(request.request_id), status: 'running', stage: '正在执行 calculate_dwell', answer: null, tool_calls: [{ name: 'calculate_dwell', arguments: {}, summary: '已读取真实轨迹', duration_ms: 2 }] })
  }
  const ctx = context(); const state = chat(ctx); const sending = state.send('计算驻留')
  await flush()
  t.mock.timers.tick(1200); await flush()
  assert.equal(reads, 1)
  assert.equal(posts, 1)
  assert.equal(state.pending.value.request_id, request.request_id)
  t.mock.timers.tick(1200); await flush()
  assert.equal(reads, 2)
  assert.equal(state.status.value, '正在执行 calculate_dwell')
  assert.equal(state.messages.value[0].result.status, 'running')
  assert.equal(state.messages.value[0].result.tool_calls[0].name, 'calculate_dwell')
  assert.equal(state.canAsk.value, false)
  ctx.value = { scene_id: 'night', zone_id: 'B', dwell_seconds: 4 }; await nextTick()
  t.mock.timers.tick(1200); await flush()
  assert.equal(state.messages.value.length, 0, 'the side channel must not put an old-scene tool result into the new scene')
  ctx.value = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3 }; await nextTick()
  assert.equal(state.messages.value[0].result.stage, '正在执行 calculate_dwell')
  finishPost(); await sending
  assert.equal(state.messages.value[0].result.status, 'complete')
  t.mock.timers.tick(6000); await flush()
  assert.equal(reads, 3, 'POST completion stops side polling')
  assert.equal(posts, 1)
})

test('a terminal polled result ends waiting even before the POST transport resolves; its late failure cannot overwrite the answer', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let failPost
  let request
  let reads = 0
  let posts = 0
  globalThis.fetch = async (url, init) => {
    if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 })
    if (url === '/api/chat') { posts++; request = JSON.parse(init.body); return new Promise((resolve, reject) => { failPost = () => reject(new TypeError('late transport error')) }) }
    reads++; return response(complete(request.request_id))
  }
  const state = chat(); const sending = state.send('生成报告')
  await flush(); t.mock.timers.tick(1200); await flush()
  assert.equal(state.messages.value[0].result.status, 'complete')
  assert.equal(state.busy.value, false)
  await sending
  failPost(); await flush(); t.mock.timers.tick(6000); await flush()
  assert.equal(reads, 1)
  assert.equal(posts, 1)
  assert.equal(state.messages.value[0].result.answer, complete(request.request_id).answer)
  assert.equal(state.connectionError.value, '')
})

test('unmounting stops side polling and a late POST leaves the saved pending request available for explicit recovery', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let finishPost
  let request
  let reads = 0
  globalThis.fetch = async (url, init) => {
    if (url === '/api/sessions') return response({ session_id: 's', remaining: 5 })
    if (url === '/api/chat') { request = JSON.parse(init.body); return new Promise(resolve => { finishPost = () => resolve(response(complete(request.request_id))) }) }
    reads++; return response({ ...complete(request.request_id), status: 'running', stage: '正在检索事件', answer: null })
  }
  const state = chat(); const sending = state.send('检索事件')
  await flush(); t.mock.timers.tick(1200); await flush()
  assert.equal(reads, 1)
  scopes[0].stop()
  t.mock.timers.tick(6000); await flush()
  assert.equal(reads, 1)
  finishPost(); await sending
  assert.equal(savedPending().request_id, request.request_id)
})
