import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/api.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', packages: 'external', write: false })
await writeFile(new URL('api.mjs', cache), bundle.outputFiles[0].text)
const { timeLabel } = await import(new URL('api.mjs', cache))

test('timestamp display matches tenth-second samples without floating-point drift', () => {
  assert.equal(timeLabel(13.1), '00:13.1')
  assert.equal(timeLabel(10.3), '00:10.3')
  assert.equal(timeLabel(59.9), '00:59.9')
})
test('rounding at minute boundaries keeps all timestamp fields consistent', () => {
  assert.equal(timeLabel(59.99), '01:00.0')
  assert.equal(timeLabel(60), '01:00.0')
  assert.equal(timeLabel(60.1), '01:00.1')
})
test('invalid and negative timestamps have a stable zero display', () => {
  for (const value of [-1, NaN, Infinity]) assert.equal(timeLabel(value), '00:00.0')
})
