import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/mediaPolicy.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('media-policy.mjs', cache), bundle.outputFiles[0].text)
const { validateMediaFile, mediaLimits } = await import(new URL('media-policy.mjs', cache))
const MiB = 1024 * 1024

test('phone photos and larger videos are allowed up to the inclusive limit', () => {
  assert.equal(validateMediaFile({ name: 'phone.JPG', size: 20 * MiB }), '')
  assert.equal(validateMediaFile({ name: 'clip.MOV', size: 200 * MiB }), '')
  assert.equal(mediaLimits.video_max_seconds, 120)
})

test('oversized, empty and unsupported files are rejected with the current limits', () => {
  assert.match(validateMediaFile({ name: 'photo.png', size: 20 * MiB + 1 }), /20MB/)
  assert.match(validateMediaFile({ name: 'clip.mp4', size: 200 * MiB + 1 }), /200MB.*2分钟/)
  assert.notEqual(validateMediaFile({ name: 'clip.webm', size: 0 }), '')
  assert.notEqual(validateMediaFile({ name: 'clip.webm', size: NaN }), '')
  assert.notEqual(validateMediaFile({ name: 'graphic.svg', size: 100 }), '')
})
