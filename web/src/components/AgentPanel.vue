<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import Icon from './Icon.vue'
import { timeLabel } from '../api'
import { useChat } from '../composables/useChat'
import { plainAnswer, chatStage } from '../plainLanguage'
import { handleChatKeydown } from '../chatKeyboard'
import type { Health, Citation, ChatContext, ChatResult, ChatMessage, Scene, Analysis } from '../types'

const props = defineProps<{ health: Health | null; context: ChatContext; suggestedQuestions?: string[]; scene?: Scene | null; analysis?: Analysis | null }>()
const questionComposing = ref(false)
function questionKeydown(event: KeyboardEvent) { handleChatKeydown(event, () => send(), questionComposing.value) }
const emit = defineEmits<{ seek: [t: number, trackId?: string]; result: [result: ChatResult] }>()
const { messages, question, busy, remaining, pending, status, connectionError, canAsk, canRetry, pendingInCurrentScope, storageAvailable, send, reconnect } = useChat(toRef(props, 'health'), toRef(props, 'context'))
const suggestions = computed(() => props.suggestedQuestions || [
  '哪些物体进入了这个区域？',
  '谁在区域里出现得最久？',
  '概括一下这段视频',
])
function jump(citation: Citation) { emit('seek', citation.t, citation.track_id) }
function displayAnswer(message: ChatMessage) { return plainAnswer(message.result, message.question, props.context, props.scene, props.analysis) }
let emittedResult = ''
watch(() => messages.value.at(-1)?.result, result => {
  if (result && (result.status === 'complete' || result.status === 'failed') && result.request_id !== emittedResult) { emittedResult = result.request_id; emit('result', result) }
}, { deep: true })
const verificationLabel = (status: string) => ({ passed: '核验通过', rejected: '核验未通过', insufficient_evidence: '证据不足' } as Record<string, string>)[status] || status
defineExpose({ sendQuestion: send, canAsk, busy })
</script>

<template>
  <aside class="agent-panel" aria-labelledby="agent-heading">
    <div class="agent-head">
      <div class="agent-mark"><Icon name="spark" :size="21" /></div>
      <div><h2 id="agent-heading">{{ context.investigation_id ? '核对这艘船' : '问问这段视频' }}</h2><p>直接提问，也能回到画面核对。</p></div>
      <span class="status-dot" :class="{ online: health?.live_agent }" :title="health?.live_agent ? '可以提问' : '暂时无法提问'"></span>
    </div>

    <div class="agent-content">
      <div v-if="!health?.live_agent" class="agent-unavailable" role="status">
        <Icon name="info" :size="18" />
        <div><strong>{{ health ? '视频问答暂不可用' : '正在连接视频问答' }}</strong><p>你仍可播放视频、查看结果和对应画面。</p></div>
      </div>

      <div v-if="messages.length === 0" class="chat-intro">
        <div class="intro-path" aria-hidden="true"><span></span><i></i><span></span><i></i><span></span></div>
        <h3 v-if="context.investigation_id">这艘船，<br />一直在那里吗？</h3>
        <h3 v-else>你想了解<br />视频里的什么？</h3>
        <p>{{ context.investigation_id ? '回看中间没能确认的画面，再判断能否确定它一直在区域内。' : '可以问出现了哪些物体、在区域里出现多久，或让助手概括一下。' }}</p>
        <div class="question-suggestions">
          <button v-for="(suggestion, index) in suggestions" :key="suggestion" :disabled="!canAsk || !!pending" @click="send(suggestion)">
            <Icon :name="['target', 'clock', 'film'][index]!" :size="17" /><span>{{ suggestion }}</span><Icon name="arrow" :size="16" />
          </button>
        </div>
        <p class="muted small">答案里的时间点可以点击回看。</p>
      </div>

      <div v-else class="chat-messages" aria-live="polite" aria-relevant="additions text">
        <article v-for="message in messages" :key="message.id" class="chat-turn">
          <div class="user-question"><span class="turn-label">你</span><p>{{ message.question }}</p></div>
          <div v-if="message.result && (message.result.answer || message.result.tool_calls?.length || message.result.public_plan?.length || message.result.verification)" class="agent-answer">
            <span class="turn-label"><Icon name="spark" :size="15" /> 回答</span>
            <p v-if="message.result.answer" class="answer-text">{{ displayAnswer(message) }}</p>
            <div v-if="message.result.citations?.length" class="citation-links">
              <button v-for="citation in message.result.citations.slice(0, 3)" :key="citation.evidence_id" @click="jump(citation)"><Icon name="play" :size="12" />回看 {{ timeLabel(citation.t) }}</button>
            </div>
            <details class="tool-details answer-details"><summary>查看分析过程</summary>
            <p v-if="message.result.answer && displayAnswer(message) !== message.result.answer" class="answer-text">{{ message.result.answer }}</p>
            <div v-if="message.result.public_plan?.length" class="public-plan"><strong>公开任务清单</strong><ol><li v-for="item in message.result.public_plan" :key="item">{{ item }}</li></ol></div>
            <details v-if="message.result.tool_calls?.length" class="tool-details">
              <summary>{{ message.result.tool_calls.length }} 次工具执行 <span>查看依据</span></summary>
              <ol><li v-for="(call, i) in message.result.tool_calls" :key="i"><code>{{ call.name }}</code><p>{{ call.summary }}</p><small>{{ call.duration_ms.toFixed(0) }} ms</small><details v-if="call.result"><summary>工具实际返回</summary><pre>{{ JSON.stringify(call.result, null, 2) }}</pre></details></li></ol>
            </details>
            <div v-if="message.result.verification" class="claim-verification" :class="message.result.verification.status"><strong>{{ verificationLabel(message.result.verification.status) }}</strong><ul><li v-for="(claim, i) in message.result.verification.claims" :key="i"><span>{{ claim.passed ? '通过' : '未通过' }}</span><p>{{ claim.description }}<small v-if="claim.value !== null">{{ claim.metric }} = {{ claim.value }}<span v-if="claim.expected !== null">；程序值 {{ claim.expected }}</span></small></p></li></ul></div>
            <details v-if="message.result.rule_citations?.length" class="tool-details"><summary>引用的判定规则</summary><p v-for="rule in message.result.rule_citations" :key="rule.id"><code>{{ rule.id }}</code> {{ rule.text }}</p></details>
            <p class="usage">{{ message.result.usage.model_calls }} 次模型调用 · {{ message.result.usage.usage_complete === false ? '已知部分用量：' : '' }}输入 {{ message.result.usage.input_tokens }} / 输出 {{ message.result.usage.output_tokens }} token<span v-if="message.result.usage.usage_complete === false">（部分调用未返回用量）</span></p>
            <p class="usage">模型：{{ health?.model }}</p>
            <div v-if="message.result.citations?.length" class="citation-links"><button v-for="citation in message.result.citations" :key="citation.evidence_id" @click="jump(citation)">{{ citation.evidence_id }} · {{ timeLabel(citation.t) }}</button></div>
            </details>
          </div>
          <p v-if="message.result?.error" class="inline-error" role="alert">{{ message.result.error.message }}</p>
          <p v-else-if="message.error" class="inline-error" role="alert">{{ message.error }}</p>
        </article>
      </div>
      <div v-if="pending && !busy" class="pending-request-note" role="status"><strong>上一个问题还在确认结果</strong><p>{{ pendingInCurrentScope ? '点击“查看上次问题进度”继续查询，不会重复提问。' : '结果会保存在原来的视频下，确认后可继续提问。' }}</p></div>
      <p v-if="busy" class="execution-state" role="status"><span class="spinner"></span><span>{{ chatStage(status) }}</span></p>
      <div v-if="connectionError && messages.length === 0" class="inline-error" role="alert">{{ connectionError }}</div>
      <button v-if="canRetry" class="button secondary reconnect" @click="reconnect"><Icon name="refresh" :size="16" />查看上次问题进度</button>
      <p v-if="!storageAvailable" class="inline-error" role="status">当前浏览器未允许保存对话，刷新前请先确认待处理请求的结果。</p>
    </div>

    <form class="chat-form" @submit.prevent="send()">
      <label class="sr-only" for="agent-question">向视频助手提问</label>
      <textarea id="agent-question" v-model="question" :disabled="!canAsk || !!pending" :placeholder="health?.live_agent ? '问一个关于当前片段的问题…' : '实时问答未启用，可先查看下方事件证据'" maxlength="500" rows="2" @compositionstart="questionComposing = true" @compositionend="questionComposing = false" @keydown="questionKeydown"></textarea>
      <div class="chat-form-bottom">
        <span>{{ remaining === null ? `可提问 ${health?.limits.session_questions ?? 10} 次` : `剩余 ${remaining} 次` }}<span class="desktop-hint"> · Enter 发送，Shift + Enter 换行</span></span>
        <button class="send-button" type="submit" :disabled="!canAsk || !!pending || !question.trim()" aria-label="发送问题"><Icon name="arrow" :size="20" /></button>
      </div>
    </form>
    <p class="agent-disclaimer">答案基于这段视频，建议结合画面核对。</p>
  </aside>
</template>
