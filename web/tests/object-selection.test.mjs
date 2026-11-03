import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/objectSelection.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('object-selection.mjs', cache), bundle.outputFiles[0].text)
const { resolveObjectNames } = await import(new URL('object-selection.mjs', cache))
const choices = [
  { id: 2, name: '汽车', label: 'car', aliases: ['车', '轿车'] },
  { id: 15, name: '猫', label: 'cat', aliases: [] },
  { id: 16, name: '狗', label: 'dog', aliases: [] },
  { id: 67, name: '手机', label: 'cell phone', aliases: ['移动电话'] },
]

test('manual names accept Chinese, English, aliases and multiple separators', () => {
  assert.deepEqual(resolveObjectNames('轿车，CAT、狗', choices, []).ids, [2, 15, 16])
  assert.deepEqual(resolveObjectNames(' CELL_PHONE ', choices, []).ids, [67])
})
test('manual names deduplicate the same model class and preserve existing selection', () => {
  const result = resolveObjectNames('车,car,汽车,狗', choices, [15])
  assert.deepEqual(result.ids, [15, 2, 16])
  assert.equal(result.error, '')
})
test('unknown object names never silently disappear or become model classes', () => {
  const result = resolveObjectNames('汽车、灭火器', choices, [15])
  assert.deepEqual(result.ids, [15])
  assert.match(result.error, /灭火器/)
})
test('fourth manual class is rejected atomically and three classes are allowed', () => {
  const result = resolveObjectNames('手机', choices, [2, 15, 16])
  assert.deepEqual(result.ids, [2, 15, 16])
  assert.match(result.error, /3/)
  assert.equal(resolveObjectNames('汽车,猫,狗', choices, []).error, '')
})
test('blank input adds nothing and asks for a name', () => {
  const result = resolveObjectNames(' 、, ', choices, [])
  assert.deepEqual(result.ids, [])
  assert.ok(result.error)
})
