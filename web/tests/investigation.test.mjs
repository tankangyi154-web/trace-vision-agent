import assert from 'node:assert/strict'
import { test, beforeEach, afterEach } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { effectScope } from 'vue'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/composables/useInvestigation.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', packages: 'external', write: false })
await writeFile(new URL('useInvestigation.mjs', cache), bundle.outputFiles[0].text)
const { useInvestigation } = await import(new URL('useInvestigation.mjs', cache))
const chatBundle = await build({ entryPoints: [fileURLToPath(new URL('../src/composables/useReviewChatContext.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', packages: 'external', write: false })
await writeFile(new URL('useReviewChatContext.mjs', cache), chatBundle.outputFiles[0].text)
const { useReviewChatContext } = await import(new URL('useReviewChatContext.mjs', cache))
class MemoryStorage { values = new Map(); getItem(k) { return this.values.get(k) ?? null } setItem(k, v) { this.values.set(k, String(v)) } }
const originalFetch = globalThis.fetch
const scopes = []
beforeEach(() => { globalThis.sessionStorage = new MemoryStorage() })
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); globalThis.fetch = originalFetch })
const response = body => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
const facts = threshold => ({ observed_seconds: 5.7, longest_interval_seconds: 3.7, span_seconds: 6.5, intervals: [{ start: 10.3, end: 12.3, censored: false }, { start: 13.1, end: 16.8, censored: true }], gaps: [{ start: 12.3, end: 13.1, duration: .8 }], verdict: threshold === 3 ? 'supported_by_observations' : 'insufficient_evidence', threshold_seconds: threshold, description: '测试返回值', evidence_ids: [] })
const investigation = threshold => ({ id: 'harbor-T001-gap', scene_id: 'harbor', track_id: 'T001', zone_id: 'A', title: '案例', question: '连续驻留有证据吗', baseline: facts(threshold), gap: { start: 12.3, end: 13.1, duration: .8, frame_start: 124, frame_end: 130 }, review_available: true, latest_review_id: null, model_status: { live_agent: false, reason: '未配置', model: 'test' } })
const job = (id, threshold, status = 'complete') => ({ review_id: id, case_id: 'harbor-T001-gap', status, stage: status === 'complete' ? '完成' : '处理真实帧', completed_frames: status === 'complete' ? 7 : 0, total_frames: 7, result: null, baseline: facts(threshold), after: status === 'complete' ? { ...facts(threshold), unknown_frames: [126], missing_evidence_times: [12.6] } : null, verification: null, error: null })
function state() { const scope = effectScope(); scopes.push(scope); return scope.run(() => useInvestigation()) }

test('3/5 threshold controls fetch actual facts and commit only the matching threshold', async () => {
  const requests = []
  globalThis.fetch = async url => { requests.push(url); return response(investigation(Number(new URL(url, 'http://local').searchParams.get('threshold')))) }
  const current = state(); await current.load()
  assert.equal(current.threshold.value, 5)
  assert.equal(current.caseData.value.baseline.verdict, 'insufficient_evidence')
  await current.setThreshold(3)
  assert.equal(current.threshold.value, 3)
  assert.equal(current.caseData.value.baseline.verdict, 'supported_by_observations')
  assert.deepEqual(requests, ['/api/investigation?threshold=5', '/api/investigation?threshold=3'])
})

test('review uses one UUID, prevents duplicate clicks and refetches facts at the selected threshold', async () => {
  let finishPost
  let posts = 0
  let payload
  const reads = []
  globalThis.fetch = async (url, init) => {
    if (url.startsWith('/api/investigation?')) return response(investigation(3))
    if (init?.method === 'POST') { posts++; payload = JSON.parse(init.body); return new Promise(resolve => { finishPost = () => resolve(response(job(payload.request_id, 5))) }) }
    reads.push(url); return response(job(payload.request_id, 3))
  }
  const current = state(); await current.setThreshold(3)
  const running = current.startReview(); await new Promise(resolve => setImmediate(resolve))
  await current.startReview()
  assert.equal(posts, 1)
  finishPost(); await running
  assert.equal(current.review.value.after.threshold_seconds, 3)
  assert.deepEqual(current.review.value.after.unknown_frames, [126])
  assert.ok(reads[0].includes('threshold=3'))
  assert.equal(current.reviewId.value, payload.request_id)
})

test('an unknown review POST can be explicitly retried with the same idempotency key after remount', async () => {
  let original
  globalThis.fetch = async (url, init) => {
    if (url.startsWith('/api/investigation?')) return response(investigation(5))
    original = JSON.parse(init.body); throw new TypeError('transport lost')
  }
  const first = state(); await first.load(); await first.startReview(); scopes[0].stop()
  let retried
  globalThis.fetch = async (url, init) => {
    if (url.startsWith('/api/investigation?')) return response(investigation(5))
    if (init?.method === 'POST') { retried = JSON.parse(init.body); return response(job(retried.request_id, 5)) }
    return response(job(retried.request_id, 5))
  }
  const restored = state(); await restored.load(); await restored.startReview()
  assert.deepEqual(retried, original)
})

test('a stale threshold response cannot overwrite a newer recomputation', async () => {
  let finishFive
  globalThis.fetch = async url => url.endsWith('=5') ? new Promise(resolve => { finishFive = () => resolve(response(investigation(5))) }) : response(investigation(3))
  const current = state(); const first = current.load(); await current.setThreshold(3)
  finishFive(); await first
  assert.equal(current.threshold.value, 3)
  assert.equal(current.caseData.value.baseline.threshold_seconds, 3)
})

test('loading historical evidence keeps the first Agent investigation fresh; only an explicit manual review binds its context', async () => {
  const current = state()
  const { chatContext, bindManualReview } = useReviewChatContext(current.threshold, current.caseData)
  globalThis.fetch = async url => url.startsWith('/api/investigation?')
    ? response({ ...investigation(5), latest_review_id: 'historical-review' })
    : response(job('historical-review', 5))
  await current.load()
  assert.equal(current.reviewId.value, 'historical-review', 'previous actual evidence is still visible')
  assert.equal(chatContext.value.review_id, null, 'history must not bypass a fresh Agent review')
  bindManualReview('explicit-manual-review')
  assert.equal(chatContext.value.review_id, 'explicit-manual-review')
  await current.load()
  assert.equal(chatContext.value.review_id, 'explicit-manual-review', 'refreshing evidence or an Agent result does not change the existing chat scope')
})
