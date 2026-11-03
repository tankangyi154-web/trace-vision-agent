import {mkdir,readFile,writeFile} from 'node:fs/promises'
await mkdir('dist/server',{recursive:true});await mkdir('dist/.openai',{recursive:true})
await writeFile('dist/server/index.js',await readFile('worker/index.js'))
await writeFile('dist/.openai/hosting.json',await readFile('.openai/hosting.json'))
console.log('Built the gateway Worker with the existing Sites artifact structure.')
