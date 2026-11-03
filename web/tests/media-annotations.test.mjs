import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const cache = new URL('../node_modules/.cache/trace-tests/', import.meta.url)
await mkdir(cache, { recursive: true })
const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/mediaAnnotations.ts', import.meta.url))], bundle: true, platform: 'node', format: 'esm', write: false })
await writeFile(new URL('media-annotations.mjs', cache), bundle.outputFiles[0].text)
const { boxesAtTime, classColor, layoutLabels, overlap } = await import(new URL('media-annotations.mjs', cache))
test('type colors do not depend on identity and common road types differ', () => {
  assert.equal(classColor('person'), '#2563eb')
  assert.notEqual(classColor('person'), classColor('car'))
  assert.match(classColor('unknown class'), /^#[0-9a-f]{6}$/)
})
test('missing frames never borrow future or stale detections', () => {
  const target = { id: '1', label: 'person', label_name: '人', samples: [{ t: 0, bbox: [0,0,.1,.1] }, { t: .6, bbox: [0,0,.2,.2] }] }
  assert.equal(boxesAtTime([target], .19, 5, false).length, 1)
  assert.equal(boxesAtTime([target], .19, 5, false)[0].text, '人 #1')
  assert.equal(boxesAtTime([target], .2, 5, false).length, 0)
  assert.equal(boxesAtTime([target], .59, 5, false).length, 0)
  assert.equal(boxesAtTime([target], .6, 5, false).length, 1)
  assert.equal(boxesAtTime([target], 40, 5, false).length, 0)
})
test('dense labels stay on screen, do not overlap, and avoid another object when space exists', () => {
  const boxes = Array.from({length:8}, (_, i) => ({ id: String(i + 20), label:'person', text:`人 #${i + 20}`, bbox:[.4+i*.018,.2,.42+i*.018,.4] }))
  const labels = layoutLabels(boxes, 600, 480)
  for (let i=0;i<labels.length;i++) {
    const a=labels[i].labelRect
    assert.ok(a[0]>=0 && a[1]>=0 && a[2]<=600 && a[3]<=480)
    for (let j=0;j<i;j++) assert.equal(overlap(a,labels[j].labelRect),0)
  }
})
