<script setup lang="ts">
import { ref } from 'vue'

interface Run {
  id: string; question: string; answer: string; case_route?: string
  tool_names: string[]; citations: unknown[]
  usage: { model_calls: number; input_tokens: number; output_tokens: number }
}
const records = ref<Run[]>([])
const recordedAt = ref('')
const model = ref('')
const loading = ref(false)
const loaded = ref(false)
const error = ref(false)

async function load() {
  if (loading.value || loaded.value) return
  loading.value = true; error.value = false
  try {
    const response = await fetch('/demos/agent-smoke.json')
    if (!response.ok) throw new Error('Unable to load records')
    const data = await response.json()
    records.value = data.records; recordedAt.value = data.recorded_at || ''; model.value = data.model || ''
    loaded.value = true
  } catch { error.value = true }
  finally { loading.value = false }
}
function onToggle(event: Event) { if ((event.currentTarget as HTMLDetailsElement).open) void load() }
</script>

<template>
  <details class="recorded-runs" @toggle="onToggle">
    <summary>查看真实运行记录</summary>
    <p class="record-note">已保存的实际问答，展开不会发起新的模型请求。</p>
    <p v-if="loading" role="status">正在读取记录…</p>
    <p v-else-if="error" role="status">暂时无法读取记录。<button @click="load">重试</button></p>
    <template v-else-if="loaded">
      <p class="record-meta">{{ recordedAt.slice(0, 10) }} · {{ model }} · {{ records.length }} 条记录</p>
      <details v-for="run in records" :key="run.id" class="record-entry">
        <summary>{{ run.question }}</summary>
        <p class="record-answer">{{ run.answer }}</p>
        <p class="record-meta">模型调用 {{ run.usage.model_calls }} 次 · 工具执行 {{ run.tool_names.length }} 次 · 证据引用 {{ run.citations.length }} 条</p>
        <p class="record-meta">工具：{{ run.tool_names.join(' → ') || '无需视觉数据工具' }}<br />输入 {{ run.usage.input_tokens }} / 输出 {{ run.usage.output_tokens }} tokens</p>
        <a :href="run.case_route === '#investigation' ? '#investigation' : '#experience'">回到案例核对</a>
      </details>
      <a href="/demos/agent-smoke.json" download="trace-agent-runs.json">下载脱敏运行记录</a>
    </template>
  </details>
</template>

<style scoped>
.recorded-runs{margin-top:30px;padding:12px 0;border-top:1px solid #e1e7ef;color:#45556e;font-size:13px;line-height:1.9}.recorded-runs summary{cursor:pointer;min-height:44px;align-content:center;font-weight:550}.record-note,.record-meta{font-size:12px;color:#69778c;overflow-wrap:anywhere}.record-entry{border-top:1px solid #e8edf4;padding:8px 0}.record-entry summary{font-size:13px;font-weight:400;line-height:1.9;padding:6px 0}.record-answer{white-space:pre-line;font-size:14px;line-height:2}.recorded-runs a,.recorded-runs button{display:inline-flex;align-items:center;min-height:44px;font-size:12px;text-underline-offset:4px}.recorded-runs button{border:0;background:none;color:#3159df;margin-left:8px;cursor:pointer}.recorded-runs :focus-visible{outline:3px solid #91aafd;outline-offset:4px}
</style>
