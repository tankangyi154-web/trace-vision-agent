import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/navigation.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('navigation.mjs', cache), bundle.outputFiles[0].text)
const { readRoute, sceneHref, demoHref, resolveSceneId } = await import(new URL('navigation.mjs', cache))

test('prepared examples deep-link separately from historical investigation scenes', () => {
  for (const id of ['daylight','lowlight','occlusion']) assert.deepEqual(readRoute(demoHref(id)),{page:'demo',sceneId:id})
  assert.equal(readRoute('#demo?scene=..%2Fprivate').sceneId,null)
})
const scenes = [{ id: 'harbor' }, { id: 'crossing' }, { id: 'night' }]

test('each case link restores its exact scene on a fresh page load', () => {
  for (const { id } of scenes) {
    const route = readRoute(sceneHref(id))
    assert.equal(route.page, 'experience')
    assert.equal(resolveSceneId(scenes, route.sceneId), id)
  }
})

test('an explicit case link overrides the previously selected scene', () => {
  assert.equal(resolveSceneId(scenes, readRoute('#experience?scene=night').sceneId, 'harbor'), 'night')
})

test('the legacy workbench link keeps the current scene or defaults to the first available scene', () => {
  assert.equal(resolveSceneId(scenes, readRoute('#experience').sceneId, 'crossing'), 'crossing')
  assert.equal(resolveSceneId(scenes, null), 'harbor')
})

test('unknown, malformed and foreign scene parameters cannot select a non-catalogue source', () => {
  assert.equal(resolveSceneId(scenes, readRoute('#experience?scene=missing').sceneId), 'harbor')
  assert.equal(readRoute('#experience?scene=..%2Fprivate').sceneId, null)
  assert.equal(readRoute('#implementation?scene=night').sceneId, null)
  assert.equal(resolveSceneId([], 'harbor'), undefined)
})

test('existing pages and unknown page fallback keep their original routes', () => {
  for (const page of ['showcase', 'assistant', 'investigation', 'evaluation', 'implementation', 'source']) {
    assert.equal(readRoute('#' + page).page, page)
  }
  assert.equal(readRoute('').page, 'showcase')
  assert.equal(readRoute('#unknown').page, 'showcase')
})
