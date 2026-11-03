import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { offlineExamples } from './buildMode'
import { installOfflineApi } from './api'
import { offlineApi } from './offlineApi'

if (offlineExamples) installOfflineApi(offlineApi)
createApp(App).mount('#app')
