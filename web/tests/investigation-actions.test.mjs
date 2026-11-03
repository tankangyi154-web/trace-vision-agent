import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/investigationActions.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', packages: 'external', write: false })
await writeFile(new URL('investigationActions.mjs', cache), bundle.outputFiles[0].text)
const { startAgentInvestigation, reviewRecordLabel } = await import(new URL('investigationActions.mjs', cache))

test('the primary investigation action dispatches the actual controlled Agent send with the current question', async () => {
  const sent = []; let scrolled = false
  const agent = { canAsk: true, sendQuestion: async question => { sent.push(question) } }
  await startAgentInvestigation(agent, '调查 T001，核查5秒结论', () => { scrolled = true })
  assert.deepEqual(sent, ['调查 T001，核查5秒结论'])
  assert.equal(scrolled, true)
})
test('an unconfigured or blocked Agent does not dispatch a paid model request', async () => {
  let sends = 0
  const agent = { canAsk: false, sendQuestion: async () => { sends++ } }
  assert.equal(await startAgentInvestigation(agent, '调查', () => {}), false)
  assert.equal(await startAgentInvestigation(null, '调查', () => {}), false)
  assert.equal(sends, 0)
})
test('an automatically loaded record is labelled as previous actual evidence with its Shanghai creation time', () => {
  const label = reviewRecordLabel('2026-10-31T13:58:09.824812+08:00', true)
  assert.match(label, /^上次实际复核记录/)
  assert.match(label, /13:58:09/)
  assert.doesNotMatch(label, /本次自动完成/)
})
