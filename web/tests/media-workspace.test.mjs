import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/mediaWorkspace.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('media-workspace.mjs', cache), bundle.outputFiles[0].text)
const { analysisHint, analysisProgress, shouldFollowMessages, isNewReply } = await import(new URL('media-workspace.mjs', cache))

test('recognition completion still explains the separate video preparation stage', () => {
  assert.match(analysisProgress({ phase: 'detecting', processed: 448, total: 585, elapsed_seconds: 300 }), /448 \/ 585.*5分0秒/)
  assert.match(analysisProgress({ phase: 'rendering', processed: 585, total: 585, elapsed_seconds: 75 }), /识别已完成.*正在整理/)
  assert.match(analysisProgress({ phase: 'queued', processed: 0, total: 0 }), /等待前一份/)
})

test('analysis guidance follows upload then targets then confirmation', () => {
  assert.match(analysisHint(false, 0, false), /上传/)
  assert.match(analysisHint(true, 0, false), /1—3/)
  assert.match(analysisHint(true, 2, true), /回车/)
  assert.equal(analysisHint(true, 3, false), '')
})
test('new answers follow the bottom but preserve a reader who scrolled up', () => {
  assert.equal(shouldFollowMessages({ scrollHeight: 1000, scrollTop: 600, clientHeight: 400 }), true)
  assert.equal(shouldFollowMessages({ scrollHeight: 1000, scrollTop: 400, clientHeight: 400 }), false)
  assert.equal(shouldFollowMessages({ scrollHeight: 300, scrollTop: 0, clientHeight: 400 }), true)
})

test('restored history is not labelled as a newly received answer', () => {
  assert.equal(isNewReply({ id: 'old', answer: 'cached answer' }, {}), false)
  assert.equal(isNewReply({ id: 'other-scene', answer: 'cached answer' }, { id: 'old' }), false)
})
test('a pending question becoming answered triggers the new-answer notice once', () => {
  assert.equal(isNewReply({ id: 'same', answer: 'new answer' }, { id: 'same' }), true)
  assert.equal(isNewReply({ id: 'same', answer: 'new answer' }, { id: 'same', answer: 'new answer' }), false)
})
