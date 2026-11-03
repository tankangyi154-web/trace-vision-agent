<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const busy = ref(false), available = ref<boolean | null>(null)
const message = ref('正在检查问答连接')
async function check() {
  if (busy.value) return
  busy.value = true
  try {
    const result = await api<{ available: boolean; message: string }>('/api/agent/connection')
    available.value = result.available; message.value = result.message
  } catch { available.value = false; message.value = '在线画面分析暂未连接，数量和时长仍可查询。' }
  finally { busy.value = false }
}
onMounted(check)
</script>
<template>
  <button class="assistant-connection" :class="{ available: available, offline: available === false }" :disabled="busy" :title="message" :aria-label="`${message} 点击检查连接`" @click="check"><i aria-hidden="true"></i>{{ busy ? '连接中' : available ? '可提问' : '检查连接' }}</button>
</template>
