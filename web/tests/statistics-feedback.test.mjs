import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/statisticsFeedback.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('statistics-feedback.mjs', cache), bundle.outputFiles[0].text)
const { statisticsFeedback, statisticsScope, validStatisticsSeconds } = await import(new URL('statistics-feedback.mjs', cache))
const scene = { zones: [{ id: 'A', name: '区域 A · 水道中部' }, { id: 'B', name: '区域 B · 右侧水面' }] }
const calculation = (zone, seconds, count, intervals) => ({ scene_id: 'harbor', zone_id: zone, dwell_seconds: seconds,
  summary: { dwell_alerts: count }, dwell: intervals.length ? [{ intervals: intervals.map(([start, end]) => ({ start, end })) }] : [] })

test('an unchanged count explains why both thresholds still qualify in the selected region', () => {
  const text = statisticsFeedback(scene, calculation('B', 3, 1, [[1, 10.4]]), calculation('B', 7, 1, [[1, 10.4]]))
  assert.match(text, /右侧水面.*7秒/)
  assert.match(text, /仍为1段/)
  assert.match(text, /9\.4秒.*仍符合/)
})

test('a stricter threshold explains a removed record using the longest continuous interval, not the sum', () => {
  const before = calculation('A', 3, 1, [[10.3, 12.3], [13.1, 16.8]])
  const after = calculation('A', 7, 0, [[10.3, 12.3], [13.1, 16.8]])
  const text = statisticsFeedback(scene, before, after)
  assert.match(text, /由1段变为0段/)
  assert.match(text, /最长连续识别3\.7秒.*未达到7秒/)
  assert.doesNotMatch(text, /5\.7|6\.5/)
})

test('different regions do not imply that the same underlying record remained unchanged', () => {
  const text = statisticsFeedback(scene, calculation('A', 3, 1, [[1, 5]]), calculation('B', 7, 1, [[1, 10.4]]))
  assert.match(text, /右侧水面.*找到1段/)
  assert.doesNotMatch(text, /仍为|由1段/)
})

test('different clips and an initial calculation do not compare unrelated counts', () => {
  const previous = { ...calculation('A', 3, 2, [[0, 8]]), scene_id: 'night' }
  for (const before of [null, previous]) {
    assert.doesNotMatch(statisticsFeedback(scene, before, calculation('A', 7, 0, [])), /仍为|由2段|最长连续识别0|undefined/)
  }
})

test('the displayed scope follows the applied analysis with a readable region name', () => {
  assert.equal(statisticsScope(scene, calculation('B', 7, 1, [])), '右侧水面 · 连续出现至少7秒')
  assert.equal(statisticsScope(scene, calculation('A', .5, 1, [])), '水道中部 · 连续出现至少0.5秒')
})

test('empty, nonnumeric and out-of-range settings cannot be submitted as valid durations', () => {
  for (const value of ['', ' ', null, undefined, NaN, Infinity, 0, .4, 61, 'abc']) assert.equal(validStatisticsSeconds(value), false)
  for (const value of [.5, 3, 7, 60, '7']) assert.equal(validStatisticsSeconds(value), true)
})
