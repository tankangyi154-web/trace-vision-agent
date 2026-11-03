import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync } from 'node:fs'

export default defineConfig({
  plugins: [vue(), {name:'prepared-examples', resolveId(id) { if(id==='virtual:prepared-examples')return '\0prepared-examples' },
    load(id) { if(id==='\0prepared-examples')return `export default ${readFileSync('../work/offline-data.json','utf8')}` } }],
  publicDir: false, base: './',
  define: { 'import.meta.env.VITE_STATIC_DEMO': JSON.stringify('true'), 'process.env.NODE_ENV': JSON.stringify('production') },
  build: { target:'es2022', outDir:'offline-dist', sourcemap:false,
    lib:{entry:'src/main.ts',name:'TraceExamples',formats:['iife'],fileName:()=>'trace-demo.js',cssFileName:'style'},
    rollupOptions:{output:{inlineDynamicImports:true}} },
})
