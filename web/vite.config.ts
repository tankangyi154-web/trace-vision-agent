import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue(), {name:'empty-offline-data',resolveId(id){if(id==='virtual:prepared-examples')return '\0empty-offline-data'},load(id){if(id==='\0empty-offline-data')return 'export default {catalog:[],examples:{}}'}}],
  define: { 'import.meta.env.VITE_STATIC_DEMO': JSON.stringify('false') },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { target: 'es2022', sourcemap: false },
})
