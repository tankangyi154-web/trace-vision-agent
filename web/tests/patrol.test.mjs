import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
async function module(name) {
  const result = await build({ entryPoints: [fileURLToPath(new URL(`../src/${name}.ts`, import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
  await writeFile(new URL(`${name}.mjs`, cache), result.outputFiles[0].text)
  return import(new URL(`${name}.mjs`, cache))
}
const { buildPatrolItems, clipRange, sampleAtTime, observedTrajectories } = await module('patrol')
const { readPatrolReviews, savePatrolReview } = await module('patrolReviews')
const { patrolDocument, patrolPayload, publicEvidenceUrl } = await module('patrolReport')
const scope = 'a'.repeat(64), otherScope = 'b'.repeat(64)
const scene = { id: 'harbor', title: '船舶案例', fps: 10, duration: 16.9, zones: [{ id: 'A', name: '区域 A · 水道中部' }, { id: 'B', name: '区域 B · 右侧水面' }], source: { title: 'Original', author: 'Author', url: 'https://example.com/video', license: 'CC BY-SA 4.0' } }
const evidence = (t, track_id = 'T001') => ({ id: `E${t}`, track_id, t, image_url: `/media/harbor/evidence/frame-${String(Math.round(t * 10)).padStart(4, '0')}.jpg` })
const event = (type, start, end = start) => ({ id: `${type}-${start}`, track_id: 'T001', type, start, end, duration: end - start })
const analysis = (zone, threshold, intervals, events) => ({ scene_id: 'harbor', zone_id: zone, dwell_seconds: threshold, review_scope_id: scope, rules_version: 'zones-v2-scoped',
  dwell: [{ track_id: 'T001', label: 'boat', intervals }], events, evidence: [1, 5, 10, 10.5, 12, 13.5, 15, 16.5].map(t => evidence(t)), summary: { tracks: 1, clip_tracks: 2 } })
const interval = (start, end, censored = false) => ({ start, end, censored })
function store(initial = null) { let value = initial; return { getItem: () => value, setItem: (_, next) => { value = next }, value: () => value } }
const record = (overrides = {}) => ({ scope, item: 'T001:1.000:10.400', status: 'checked', note: '人工核对说明', updatedAt: '2026-11-02T03:00:00.000Z', ...overrides })

test('one regional appearance groups its duration and exit without fabricating an entry', () => {
  const data = analysis('B', 7, [interval(1, 10.4)], [event('initial_presence', 1), event('dwell', 1, 10.4), event('exit', 10.5)])
  const items = buildPatrolItems(scene, data)
  assert.equal(items.length, 1); const item = items[0]
  assert.equal(item.kind, 'duration'); assert.equal(item.longest, 9.4); assert.equal(item.end, 10.5)
  assert.match(item.description, /右侧水面.*9\.4秒.*7秒/)
  assert.ok(item.facts.includes('进入时间尚未确认'))
  assert.equal(item.gaps.length, 0); assert.equal(item.canInvestigate, false)
})

test('a gap can group an episode but cannot turn its accumulated total into continuous evidence', () => {
  const data = analysis('A', 5, [interval(10.3, 12.3, true), interval(13.1, 16.8, true)], [event('enter', 10.3), event('observation_gap', 12.3, 13.1), event('initial_presence', 13.1)])
  const [item] = buildPatrolItems(scene, data)
  assert.equal(item.kind, 'gap'); assert.equal(item.observed, 5.7); assert.equal(item.longest, 3.7)
  assert.match(item.description, /0\.8秒.*3\.7秒.*无法确认连续达到5秒/)
  assert.equal(item.canInvestigate, true)
  assert.ok(item.evidence.every(e => e.track_id === 'T001' && e.t >= 9.8))
  assert.doesNotMatch(item.description, /连续识别5\.7秒/)
})

test('a real exit and re-entry remain separate appearances', () => {
  const data = analysis('A', 1, [interval(1, 2), interval(4, 6)], [event('enter', 1), event('exit', 2.1), event('enter', 4), event('exit', 6.1)])
  assert.equal(buildPatrolItems(scene, data).length, 2)
})

test('a short initial presence alone does not become a manufactured incident', () => {
  const data = analysis('A', 7, [interval(1, 1.2)], [event('initial_presence', 1)])
  assert.deepEqual(buildPatrolItems(scene, data), [])
})

test('a point entry gets nearby playback context without acquiring a fabricated observed duration', () => {
  const data = analysis('A', 7, [interval(1, 1, true)], [event('enter', 1)])
  const [item] = buildPatrolItems(scene, data)
  assert.equal(item.longest, 0)
  assert.ok(item.end > item.start)
  assert.equal(item.kind, 'movement')
})

test('evidence cannot be borrowed from a different target or a far-away timestamp', () => {
  const data = analysis('B', 7, [interval(1, 10.4)], [event('exit', 10.5)])
  data.evidence = [evidence(5, 'T999'), evidence(16)]
  assert.deepEqual(buildPatrolItems(scene, data)[0].evidence, [])
})

test('clip playback rejects invalid ranges and keeps valid ranges within the real video', () => {
  assert.deepEqual(clipRange(-1, 20, 16.9), { start: 0, end: 16.9 })
  for (const values of [[3, 2, 16], [2, 2, 16], [NaN, 4, 16], [0, Infinity, 16], [20, 25, 16]]) assert.equal(clipRange(...values), null)
})

test('selection overlays use the actual video frame and never fill a missing or future observation', () => {
  const track = { samples: [12.2, 12.3, 13.1, 13.2].map(t => ({ t, frame: Math.round(t * 10), bbox: [.1, .1, .2, .2] })) }
  assert.equal(sampleAtTime(track, 12.399, 10).t, 12.3)
  assert.equal(sampleAtTime(track, 12.6, 10), null)
  assert.equal(sampleAtTime(track, 13.099, 10), null)
  assert.equal(sampleAtTime(track, 13.1, 10).t, 13.1)
})

test('trajectory drawings split at an unresolved gap and stay within the selected playback range', () => {
  const track = { samples: [1, 1.1, 12.2, 12.3, 13.1, 13.2].map(t => ({ t, frame: Math.round(t * 10), bbox: [t / 100, .1, t / 100 + .1, .2] })) }
  assert.equal(observedTrajectories(track, 10).length, 3)
  assert.equal(observedTrajectories(track, 10, { start: 12, end: 14 }).length, 2)
  assert.equal(observedTrajectories(track, 10, { start: 0, end: 2 }).length, 1)
})

test('saved human opinions are isolated by the entire data/rule scope and can be restored', () => {
  const storage = store(); assert.equal(savePatrolReview(storage, record()), true)
  assert.equal(readPatrolReviews(storage, otherScope).records[record().item], undefined)
  savePatrolReview(storage, record({ scope: otherScope, status: 'uncertain', note: '新设置仍无法确认' }))
  assert.equal(readPatrolReviews(storage, scope).records[record().item].status, 'checked')
  assert.equal(readPatrolReviews(storage, otherScope).records[record().item].status, 'uncertain')
})

test('denied or corrupt storage cannot pretend that records were persisted', () => {
  const denied = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  assert.equal(readPatrolReviews(denied, scope).available, false)
  assert.equal(savePatrolReview(denied, record()), false)
  assert.equal(readPatrolReviews(store('{broken'), scope).available, false)
})

test('invalid records do not reach storage and history remains bounded', () => {
  const storage = store()
  for (const values of [{ scope: 'other' }, { status: 'approved' }, { note: 'x'.repeat(1201) }]) assert.throws(() => savePatrolReview(storage, record(values)))
  assert.equal(storage.value(), null)
  const old = Array.from({ length: 400 }, (_, i) => record({ item: `item-${i}` }))
  const full = store(JSON.stringify(old)); savePatrolReview(full, record())
  assert.equal(JSON.parse(full.value()).length, 400)
})

test('portable evidence documents escape human notes and only embed real raster data', () => {
  const data = analysis('B', 7, [interval(1, 10.4)], [event('exit', 10.5)])
  const items = buildPatrolItems(scene, data)
  const malicious = record({ note: '<script>window.pwned=1</script>\n人工说明', item: items[0].id })
  const html = patrolDocument(scene, data, items, { [malicious.item]: malicious }, { E1: 'data:image/jpeg;base64,YWJj', E5: 'data:image/svg+xml;base64,PHN2Zz4=' }, 'http://127.0.0.1:8000')
  assert.ok(html.includes('&lt;script&gt;window.pwned=1&lt;/script&gt;'))
  assert.doesNotMatch(html, /<script>|data:image\/svg/)
  assert.match(html, /data:image\/jpeg;base64,YWJj/)
  assert.match(html, /已核对1条/)
})

test('a foreign saved opinion cannot appear in the current document', () => {
  const data = analysis('B', 7, [interval(1, 10.4)], [event('exit', 10.5)])
  const items = buildPatrolItems(scene, data)
  assert.equal(patrolPayload(scene, data, items, { [items[0].id]: record({ scope: otherScope }) }).items[0].manual_review, null)
})

test('evidence export cannot fetch external, authenticated or traversal URLs', () => {
  const valid = '/media/harbor/evidence/frame-0010.jpg'
  assert.equal(publicEvidenceUrl(valid, 'harbor', 'http://127.0.0.1:8000'), 'http://127.0.0.1:8000' + valid)
  for (const path of ['https://evil.example/a.jpg', '/media/night/evidence/frame-0010.jpg', '/media/harbor/evidence/../private.jpg', '/media/harbor/evidence/frame-0010.jpg?token=x']) assert.equal(publicEvidenceUrl(path, 'harbor', 'http://127.0.0.1:8000'), null)
  assert.equal(publicEvidenceUrl(valid, 'harbor', 'https://user:pass@example.com'), null)
})
