import assert from 'node:assert/strict'
import { test, beforeEach } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/mediaPersistence.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('media-persistence.mjs', cache), bundle.outputFiles[0].text)
const { MEDIA_CACHE, emptyMediaCache, readMediaCache, writeMediaCache, parseMediaCache, isMissingMedia, rememberMediaRecord, readMediaRecords, forgetMediaRecord } = await import(new URL('media-persistence.mjs', cache))
class MemoryStorage { values = new Map(); getItem(key) { return this.values.get(key) ?? null } setItem(key, value) { this.values.set(key, String(value)) } removeItem(key) { this.values.delete(key) } }
beforeEach(() => { globalThis.sessionStorage = new MemoryStorage(); globalThis.localStorage = new MemoryStorage() })
const record = { id: '11111111-1111-4111-8111-111111111111', owner: 'local-owner-'.padEnd(40,'x') }

test('refresh and a new tab restore job ownership, classes and video position', () => {
  const state = { ...emptyMediaCache(), job: record, classIds: [0, 2], time: 19.2, target: '30', panel: 'chat' }
  assert.ok(writeMediaCache(state)); assert.deepEqual(readMediaCache(), state)
  globalThis.sessionStorage = new MemoryStorage()
  assert.deepEqual(readMediaCache(), state)
})
test('legacy tab references migrate without requiring another upload', () => {
  sessionStorage.setItem('trace-media-job-v1', JSON.stringify(record))
  assert.deepEqual(readMediaCache().job, record)
  writeMediaCache(readMediaCache())
  assert.equal(sessionStorage.getItem('trace-media-job-v1'), null)
  assert.ok(localStorage.getItem(MEDIA_CACHE))
})
test('a corrupt tab cache and unavailable storage fall back to the valid copy', () => {
  writeMediaCache({ ...emptyMediaCache(), job: record })
  sessionStorage.setItem(MEDIA_CACHE, '{bad json')
  assert.deepEqual(readMediaCache().job, record)
  sessionStorage.setItem = () => { throw new Error('storage blocked') }
  assert.ok(writeMediaCache({ ...emptyMediaCache(), classIds: [0] }))
})
test('invalid references and out of range choices are not restored', () => {
  const state = parseMediaCache(JSON.stringify({ version: 2, job: { id: '../escape', owner: record.owner }, classIds: [0, 0, 2, true, 99, -1], target: 'not-an-id', time: -4 }))
  assert.equal(state.job, null); assert.equal(state.target, null); assert.equal(state.time, 0)
  assert.deepEqual(state.classIds, [0, 2])
})
test('transport errors and gateway 404s never count as confirmed deletion', () => {
  for (const error of [new TypeError('offline'), { status: 503, code: 'unavailable' }, { status: 404, code: 'HTTP_404' }]) assert.equal(isMissingMedia(error), false)
  assert.equal(isMissingMedia({ status: 404, code: 'not_found' }), true)
})
test('clearing the workspace does not remove records; deleting one preserves the others', () => {
  const other = { ...record, id: '22222222-2222-4222-8222-222222222222' }
  rememberMediaRecord(record); rememberMediaRecord(other); rememberMediaRecord(record)
  writeMediaCache(emptyMediaCache())
  assert.equal(readMediaRecords().length, 2)
  forgetMediaRecord(record.id)
  assert.deepEqual(readMediaRecords(), [other])
})
