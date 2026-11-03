import assert from 'node:assert/strict'
import { test } from 'node:test'
import { build } from 'esbuild'
import { mkdir,writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const cache=new URL('../node_modules/.cache/trace-tests/',import.meta.url)
await mkdir(cache,{recursive:true})
const bundle=await build({entryPoints:[fileURLToPath(new URL('../src/mediaScope.ts',import.meta.url))],bundle:true,platform:'node',format:'esm',write:false})
await writeFile(new URL('media-scope.mjs',cache),bundle.outputFiles[0].text)
const {validMediaScope}=await import(new URL('media-scope.mjs',cache))
test('selected video ranges require finite times and a known duration boundary',()=>{
 assert.equal(validMediaScope({start_seconds:2,end_seconds:5},20),true)
 for(const value of [null,{}, {start_seconds:5,end_seconds:2},{start_seconds:0,end_seconds:NaN},{start_seconds:0,end_seconds:21},{start_seconds:-1,end_seconds:5}])assert.equal(validMediaScope(value,20),false)
})
