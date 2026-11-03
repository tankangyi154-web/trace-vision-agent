import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/plainLanguage.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('plain-language.mjs', cache), bundle.outputFiles[0].text)
const { plainAnswer, targetName, objectName, eventDescription, chatStage } = await import(new URL('plain-language.mjs', cache))
const context = { scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3 }
const scene = { id: 'harbor' }
const evidence = { id: 'harbor-T001-f0105', track_id: 'T001', t: 10.5 }
const calculation = () => ({ scene_id: 'harbor', zone_id: 'A', dwell_seconds: 3, evidence: [evidence], events: [],
  dwell: [{ track_id: 'T001', label: 'boat', observed_seconds: 5.7, intervals: [{ start: 10.3, end: 12.3, censored: true }, { start: 13.1, end: 16.8, censored: true }] }] })
const answer = () => ({ status: 'complete', answer: '原始技术说明：累计可观测驻留5.7秒，证据：harbor-T001-f0105。', citations: [{ evidence_id: evidence.id, track_id: evidence.track_id }], tool_calls: [{ name: 'calculate_dwell', arguments: {} }], error: null })

test('the short longest-appearance answer keeps the actual total and its uncertainty without code identifiers', () => {
  const original = answer(); const text = plainAnswer(original, '哪个目标驻留最久？', context, scene, calculation())
  assert.match(text, /1号船.*5\.7秒/)
  assert.match(text, /中间.*没识别到.*无法确认/)
  assert.doesNotMatch(text, /harbor|T001|boat|censored|6\.5/)
  assert.ok(text.length < 100)
  assert.match(original.answer, /harbor-T001-f0105/, 'the full source answer is preserved for details')
})

test('a continuous-duration question is never replaced by an accumulated-duration summary', () => {
  const result = answer(); result.answer = '最长连续识别到3.7秒，不能据此确认连续超过5秒。'
  const text = plainAnswer(result, '最长连续停留多久？', context, scene, calculation())
  assert.equal(text, result.answer)
  assert.doesNotMatch(text, /5\.7/)
})

test('ties are not presented as a unique longest object', () => {
  const data = calculation(); data.dwell.push({ ...data.dwell[0], track_id: 'T002' })
  assert.match(plainAnswer(answer(), '谁出现最久？', context, scene, data), /并列/)
})

test('refusals, failed results and investigation verdicts retain their original meaning', () => {
  for (const fields of [{ insufficient_evidence: true }, { status: 'failed', error: { message: '未完成' } }, { verification: { status: 'insufficient_evidence' } }]) {
    const result = { ...answer(), ...fields, answer: '不能确认它一直在这里。' }
    assert.equal(plainAnswer(result, '谁停留最久？', context, scene, calculation()), result.answer)
  }
  const result = { ...answer(), answer: '复核后仍不能确认连续超过五秒。' }
  assert.equal(plainAnswer(result, '谁停留最久？', { ...context, investigation_id: 'review' }, scene, calculation()), result.answer)
})

test('a different scope or uncited target cannot generate a new short factual claim', () => {
  for (const data of [{ ...calculation(), zone_id: 'B' }, { ...calculation(), dwell_seconds: 5 }, { ...calculation(), scene_id: 'night' }]) {
    const result = { ...answer(), answer: '保留原回答。' }
    assert.equal(plainAnswer(result, '谁出现最久？', context, scene, data), result.answer)
  }
  const result = { ...answer(), answer: '保留原回答。', citations: [{ evidence_id: 'foreign', track_id: 'T002' }] }
  assert.equal(plainAnswer(result, '谁出现最久？', context, scene, calculation()), result.answer)
})

test('first presence and reappearance are not counted as entry', () => {
  const data = calculation(); data.events = [{ type: 'initial_presence', track_id: 'T001', label: 'boat' }]
  const result = { ...answer(), answer: '没有看到进入。', tool_calls: [{ name: 'search_events', arguments: { event_type: 'all' } }] }
  assert.equal(plainAnswer(result, '进入了几次？', context, scene, data), result.answer)
  data.events.push({ type: 'enter', track_id: 'T001', label: 'boat' })
  assert.match(plainAnswer(result, '进入了几次？', context, scene, data), /1次/)
})

test('a limited per-target query cannot be presented as the whole-region ranking', () => {
  const result = { ...answer(), answer: '保留原回答。', tool_calls: [{ name: 'calculate_dwell', arguments: { track_id: 'T001' } }] }
  assert.equal(plainAnswer(result, '谁出现最久？', context, scene, calculation()), result.answer)
})

test('negative, conditional and qualified questions are not replaced by a generic summary', () => {
  const result = { ...answer(), answer: '保留对具体问题的回答。', tool_calls: [...answer().tool_calls, { name: 'search_events', arguments: {} }] }
  for (const question of ['谁出现最久，超过十秒了吗？', '最久的汽车在哪里？', '哪些物体没有进入这个区域？', '船进入区域后又出来了吗？']) {
    assert.equal(plainAnswer(result, question, context, scene, calculation()), result.answer)
  }
})

test('ordinary names and event descriptions preserve ambiguity without internal terms', () => {
  assert.equal(targetName('T001', 'boat'), '1号船')
  assert.equal(objectName('unrecognised-label'), '物体')
  assert.match(eventDescription({ type: 'observation_gap' }, 3), /没有识别到.*不能确定/)
  assert.match(eventDescription({ type: 'initial_presence' }, 3), /进入时间不确定/)
  assert.doesNotMatch(chatStage('执行工具 calculate_dwell (1/5)'), /calculate_dwell|工具/)
})
