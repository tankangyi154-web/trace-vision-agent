import assert from 'node:assert/strict'
import {test} from 'node:test'
import {build} from 'esbuild'
import {mkdir,writeFile} from 'node:fs/promises'
import {fileURLToPath} from 'node:url'
const cache=new URL('../node_modules/.cache/trace-tests/',import.meta.url)
await mkdir(cache,{recursive:true})
const bundle=await build({entryPoints:[fileURLToPath(new URL('../src/chatKeyboard.ts',import.meta.url))],bundle:true,platform:'node',format:'esm',write:false})
await writeFile(new URL('chat-keyboard.mjs',cache),bundle.outputFiles[0].text)
const {handleChatKeydown}=await import(new URL('chat-keyboard.mjs',cache))
function press(values={},composing=false){
 let sends=0,prevented=false
 handleChatKeydown({key:'Enter',shiftKey:false,isComposing:false,keyCode:13,repeat:false,preventDefault(){prevented=true},...values},()=>sends++,composing)
 return {sends,prevented}
}
test('Enter sends once and does not insert a newline',()=>assert.deepEqual(press(),{sends:1,prevented:true}))
test('Shift Enter keeps normal editing without sending',()=>assert.deepEqual(press({shiftKey:true}),{sends:0,prevented:false}))
test('Chinese composition confirmation is never submitted',()=>{
 for(const result of [press({isComposing:true}),press({keyCode:229}),press({},true)])assert.deepEqual(result,{sends:0,prevented:false})
})
test('holding Enter cannot start another request',()=>assert.deepEqual(press({repeat:true}),{sends:0,prevented:true}))
test('ordinary typing is left untouched',()=>assert.deepEqual(press({key:'a',keyCode:65}),{sends:0,prevented:false}))
