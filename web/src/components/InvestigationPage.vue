<script setup lang="ts">
import { demoPoster } from '../demoPosters'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Icon from './Icon.vue'
import AgentPanel from './AgentPanel.vue'
import EvidenceTimeline from './EvidenceTimeline.vue'
import { useInvestigation } from '../composables/useInvestigation'
import { useReviewChatContext } from '../composables/useReviewChatContext'
import { timeLabel } from '../api'
import { reviewRecordLabel, startAgentInvestigation } from '../investigationActions'
import type { ChatResult, Health, ReviewFrame } from '../types'
import '../investigation.css'

const props = defineProps<{ health: Health | null }>()
const { caseData, review, reviewId, threshold, loading, submitting, polling, reviewBusy, canRun, requestPending, error, load, setThreshold, startReview, reconnect } = useInvestigation()
const player = ref<HTMLVideoElement | null>(null)
const playerContainer = ref<HTMLElement | null>(null)
const agentPanel = ref<InstanceType<typeof AgentPanel> | null>(null)
const agentSection = ref<HTMLElement | null>(null)
const previousRecord = ref(true)
const currentTime = ref(0)
const playbackSrc = computed(() => caseData.value?.playback_url || caseData.value?.original_url || '')
const isPlaybackCopy = computed(() => !!caseData.value?.playback_url && caseData.value.playback_url !== caseData.value.original_url)
const showRegion = ref(true)
const mediaError = ref(false)
const selectedFrameNumber = ref<number | null>(null)
const overlayMode = ref<'overlay' | 'crop'>('overlay')
let pendingSeek = 0
const frames = computed(() => review.value?.result?.frames || [])
const selectedFrame = computed<ReviewFrame | null>(() => frames.value.find(frame => frame.frame === selectedFrameNumber.value) || frames.value.find(frame => !frame.accepted) || frames.value[0] || null)
const unknownFrames = computed(() => review.value?.after?.unknown_frames || frames.value.filter(frame => !frame.accepted).map(frame => frame.frame))
const unknownTimes = computed(() => review.value?.after?.missing_evidence_times || frames.value.filter(frame => !frame.accepted).map(frame => frame.t))
const modelHealth = computed<Health | null>(() => !caseData.value ? props.health : ({
  status: props.health?.status || 'ok', mode: props.health?.mode || 'local', version: props.health?.version || '0.1.0',
  limits: props.health?.limits || { session_questions: 5, daily_questions: 50 },
  live_agent: caseData.value.model_status.live_agent,
  reason: caseData.value.model_status.reason, model: caseData.value.model_status.model,
}))
const { chatContext, bindManualReview } = useReviewChatContext(threshold, caseData)
const suggestions = computed(() => [
  `检查 T001 的观测缺口，必要时局部复核，再判断连续驻留是否超过 ${threshold.value} 秒`,
  '把阈值改成3秒，结论会怎样？',
  '还缺哪些证据？为什么不能证明物理连续？',
])
const rangeStart = computed(() => Math.min(...(caseData.value?.baseline.intervals.map(interval => interval.start) || [0]), caseData.value?.gap.start || 0))
const rangeEnd = computed(() => Math.max(...(caseData.value?.baseline.intervals.map(interval => interval.end) || [1]), caseData.value?.gap.end || 1))
const polygon = computed(() => caseData.value?.region_polygon.map(point => `${point[0]! * 1000},${point[1]! * 1000}`).join(' '))
const insideGap = computed(() => !!caseData.value && currentTime.value > caseData.value.gap.start && currentTime.value < caseData.value.gap.end)
const auditUrl = computed(() => `/api/investigation/report?${new URLSearchParams({ ...(reviewId.value ? { review_id: reviewId.value } : {}), threshold: String(threshold.value) })}`)
const canInvestigate = computed(() => !!modelHealth.value?.live_agent && !!agentPanel.value?.canAsk && !loading.value)
const verdict = (value: string) => value === 'supported_by_observations' ? '观测支持当前阈值' : '证据不足以支持当前阈值'
function seek(t: number) {
  pendingSeek = t
  currentTime.value = t
  if (player.value && player.value.readyState >= 1) player.value.currentTime = t
}
function locate(t: number) { seek(t); playerContainer.value?.scrollIntoView({ block: 'start' }) }
function selectFrame(frame: ReviewFrame) { selectedFrameNumber.value = frame.frame; seek(frame.t) }
async function runReview() { previousRecord.value = false; await startReview(); if (reviewId.value) bindManualReview(reviewId.value) }
async function investigate() {
  await startAgentInvestigation(agentPanel.value, suggestions.value[0]!, () => agentSection.value?.scrollIntoView({ block: 'start' }))
}
async function onAgentResult(result: ChatResult) {
  const calledReview = result.tool_calls.find(call => call.name === 'review_gap' && typeof call.result?.review_id === 'string')
  const id = result.review_id || calledReview?.result?.review_id
  if (id) {
    // Keep the ongoing model conversation in its original scope. Its actual
    // review tool result updates the evidence view without erasing that answer.
    if (String(id) !== reviewId.value) previousRecord.value = false
    await load(threshold.value, String(id))
  }
}
watch(() => review.value?.result, () => { selectedFrameNumber.value = frames.value.find(frame => !frame.accepted)?.frame ?? frames.value[0]?.frame ?? null })
watch(playbackSrc, async src => {
  pendingSeek = player.value?.currentTime ?? currentTime.value
  mediaError.value = false
  await nextTick()
  if (src) player.value?.load()
}, { flush: 'sync' })
onMounted(async () => {
  await load()
  pendingSeek = caseData.value?.gap.start || 0
  await nextTick()
  seek(pendingSeek)
})
</script>

<template>
  <div class="investigation-page page-width">
    <header class="investigation-heading"><div><p class="case-kicker">单案例证据调查 · harbor / T001 / 区域 A</p><h1>{{ caseData?.question || '连续驻留的结论，证据够吗？' }}</h1><p>先看观测在哪里中断，再回到原始帧复核。未知的部分，始终保留。</p></div><a href="#experience" class="text-button">打开原工作台 <Icon name="arrow" :size="15" /></a></header>

    <div v-if="!caseData && loading" class="loading-state" role="status"><span class="spinner"></span>读取案例、基线时序与本地复核状态</div>
    <div v-else-if="!caseData" class="page-error" role="alert"><h2>案例暂时没有载入</h2><p>{{ error }}</p><button class="button primary" @click="load()">重新读取</button></div>
    <template v-else>
      <div class="investigation-mode-note" :class="{ 'model-pending': !modelHealth?.live_agent }"><Icon :name="modelHealth?.live_agent ? 'check' : 'info'" :size="18" /><p><strong>{{ modelHealth?.live_agent ? '本地视觉工具与真实模型入口已启用' : '算法/工具可演示，真实模型闭环待配置' }}</strong><span>本页复核会实际处理缺口帧；程序结论与模型回答分开展示。文本模型只读取结构化观测，不读取图片。</span></p></div>

      <div class="investigation-primary">
        <section ref="playerContainer" class="investigation-video" aria-labelledby="case-video-heading">
          <div class="investigation-video-heading"><h2 id="case-video-heading">先回到这 {{ caseData.gap.duration.toFixed(1) }} 秒</h2><label><input v-model="showRegion" type="checkbox" />显示区域 A</label></div>
          <div class="investigation-video-stage"><video ref="player" :src="playbackSrc" :poster="demoPoster('harbor', caseData.poster_url)" controls playsinline preload="metadata" :aria-label="isPlaybackCopy ? '船舶目标 T001 兼容播放副本' : '船舶目标 T001 原始视频'" @timeupdate="currentTime = player?.currentTime || 0" @loadedmetadata="seek(pendingSeek)" @error="mediaError = true"></video><svg v-if="showRegion" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true"><polygon :points="polygon" fill="rgba(65,123,255,.1)" stroke="#a8c0ff" stroke-width="2.5" stroke-dasharray="10 7" /></svg><span class="investigation-video-label">{{ isPlaybackCopy ? '兼容播放副本' : '原始视频' }} · 目标 T001</span><span v-if="insideGap" class="investigation-gap-label">原索引中的未知窗口</span><div v-if="mediaError" class="media-error"><p>视频未加载</p><button class="button secondary" @click="player?.load(); mediaError = false">重新加载</button></div></div>
          <div class="investigation-playhead"><span>{{ timeLabel(currentTime) }} / {{ timeLabel(caseData.duration) }}</span><div><button @click="seek(caseData.gap.start)"><Icon name="play" :size="12" />缺口前 {{ timeLabel(caseData.gap.start) }}</button><button @click="seek(caseData.gap.end)"><Icon name="play" :size="12" />重新观测 {{ timeLabel(caseData.gap.end) }}</button></div></div>
          <div class="investigation-baseline-copy"><p v-if="isPlaybackCopy">兼容播放副本；取证帧仍来自固定原始视频。</p><strong>基线已正确保留缺口</strong><p>从原始索引到当前结果，不把缺帧补成轨迹。下面只回查 {{ caseData.gap.frame_start }}–{{ caseData.gap.frame_end }} 帧，使用固定模型、ROI 和关联门控。</p></div>
        </section>

        <section class="investigation-question" aria-labelledby="current-facts-heading">
          <div class="investigation-threshold"><span>当前判定阈值</span><div role="group" aria-label="重算驻留阈值"><button v-for="value in [3, 5]" :key="value" :aria-pressed="threshold === value" :disabled="loading || reviewBusy" @click="setThreshold(value as 3 | 5)">{{ value }} 秒</button></div></div>
          <h2 id="current-facts-heading">基线：{{ verdict(caseData.baseline.verdict) }}</h2><p>{{ caseData.baseline.description }}</p>
          <dl class="case-facts"><div><dt>最长有效观测段</dt><dd>{{ caseData.baseline.longest_interval_seconds.toFixed(1) }}<small> 秒</small></dd></div><div><dt>已累计观测</dt><dd>{{ caseData.baseline.observed_seconds.toFixed(1) }}<small> 秒</small></dd></div><div class="unknown-fact"><dt>待核查的缺口</dt><dd>{{ caseData.gap.duration.toFixed(1) }}<small> 秒</small></dd></div></dl>
          <div class="investigation-run"><div class="investigation-run-actions"><button class="button primary" :disabled="!canInvestigate" @click="investigate"><Icon name="spark" :size="17" />让 Agent 调查并复核</button><button class="button secondary" :disabled="!canRun" @click="runReview"><Icon :name="reviewBusy ? 'clock' : 'target'" :size="16" />{{ submitting ? '正在提交本地任务' : reviewBusy ? '本地复核执行中' : requestPending ? '恢复同一次本地复核' : '仅运行本地视觉复核' }}</button></div><p v-if="!modelHealth?.live_agent" class="agent-action-unavailable">暂时无法自动调查，可先回看并复核画面。</p><p v-else-if="!canInvestigate">Agent 当前不可提交新问题，可在下方查看执行、剩余额度或原请求状态。</p><p>Agent 主按钮会发送真实模型请求；本地复核次按钮仅使用 CPU。<br />固定 ROI / YOLO11n · {{ caseData.gap.frame_end - caseData.gap.frame_start + 1 }} 帧 · 不降低阈值追求检出。</p></div>
          <p v-if="!caseData.review_available" class="inline-error">{{ caseData.review_reason || '当前环境未提供本地视觉运行器。' }}</p>
          <div v-if="review" class="review-record-label"><strong>{{ reviewRecordLabel(review.created_at, previousRecord) }}</strong><p v-if="previousRecord">这里读取已有真实结果，不表示本次已自动执行新的调查。</p></div>
          <div v-if="submitting || review" class="investigation-job-state" role="status"><span v-if="submitting || polling" class="spinner"></span><div><strong>{{ submitting ? '请求已发送，等待本地任务状态' : review?.stage }}</strong><p v-if="review">已处理 {{ review.completed_frames }} / {{ review.total_frames }} 帧<span v-if="review.status === 'failed'"> · 执行失败</span></p></div></div>
          <p v-if="review?.error" class="inline-error" role="alert">{{ review.error.message }}</p>
          <div v-if="error" class="investigation-error" role="alert"><p>{{ error }}</p><button class="text-button" @click="reconnect">重新连接原复核任务</button></div>
        </section>
      </div>

      <section class="investigation-timelines" aria-labelledby="temporal-evidence-heading"><div class="investigation-section-title"><div><h2 id="temporal-evidence-heading">前后用同一条时间轴对照</h2><p>点区间定位视频。条带表示程序规则区间，灰色和橙色保留未知与未决。</p></div><span v-if="loading" class="execution-state"><span class="spinner"></span>正在按阈值重新计算</span></div><EvidenceTimeline :facts="caseData.baseline" label="复核前" :start="rangeStart" :end="rangeEnd" @seek="locate" /><EvidenceTimeline v-if="review?.after" :facts="review.after" label="复核后" :start="rangeStart" :end="rangeEnd" :unknown-times="unknownTimes" reviewed @seek="locate" /><div v-else class="review-timeline-empty">运行复核后，才会出现实际复算结果。</div><div class="temporal-conclusion" v-if="review?.after && review.result"><div><span>规则合并最长区间</span><strong>{{ review.after.longest_interval_seconds.toFixed(1) }}<small> 秒</small></strong></div><div><span>候选纳入</span><strong>{{ review.result.summary.accepted_frames }}<small> / {{ review.result.summary.reviewed_frames }} 帧</small></strong></div><div class="unknown-fact"><span>仍未解决</span><strong>{{ review.result.summary.unresolved_frames }}<small> 帧</small></strong></div><p><strong>{{ verdict(review.after.verdict) }}</strong>{{ review.after.description }}<span v-if="unknownFrames.length">未决帧：{{ unknownFrames.join('、') }}。区间被容忍规则合并，不等于每帧已证实，更不等于物理连续或身份已确认。</span><span v-else>几何候选的关联仍是算法假设，不是物理连续或真实身份的证明。</span></p></div></section>

      <section class="investigation-frame-section" aria-labelledby="frame-review-heading"><div class="investigation-section-title"><div><h2 id="frame-review-heading">逐帧看，复检究竟补了什么</h2><p>左侧原始缺口帧，右侧实际检测投影。未通过关联门控的帧仍保持未决。</p></div><a v-if="review?.status === 'complete'" class="button secondary" :href="auditUrl" download><Icon name="download" :size="16" />下载 JSON 证据包</a></div>
        <div v-if="!frames.length" class="investigation-frame-empty"><Icon name="film" :size="27" /><p>{{ reviewBusy ? '复核正在执行，等待实际帧与检测结果。' : '尚未生成复核证据。点击上方按钮实际处理这段缺口。' }}</p></div>
        <template v-else-if="selectedFrame"><div class="review-frame-tabs" role="group" aria-label="选择复核帧"><button v-for="frame in frames" :key="frame.frame" :aria-pressed="selectedFrame.frame === frame.frame" :class="{ unresolved: !frame.accepted }" @click="selectFrame(frame)"><strong>{{ timeLabel(frame.t) }}</strong><span>帧 {{ frame.frame }}</span><small>{{ frame.accepted ? '候选纳入' : '关联未决' }}</small></button></div><div class="review-frame-comparison"><figure><figcaption><strong>原始缺口帧</strong><button class="timestamp" @click="locate(selectedFrame.t)"><Icon name="play" :size="12" />{{ timeLabel(selectedFrame.t) }}</button></figcaption><img :src="selectedFrame.original_image" :alt="`原始帧${selectedFrame.frame}，${timeLabel(selectedFrame.t)}`" /><p>基线索引在此帧没有 T001 的有效观测，不代表画面中没有船舶。</p></figure><figure><figcaption><strong>{{ overlayMode === 'overlay' ? '实际复检投影' : '实际检测 ROI' }}</strong><div class="segmented" role="group" aria-label="复检证据显示"><button :aria-pressed="overlayMode === 'overlay'" @click="overlayMode = 'overlay'">全图投影</button><button :aria-pressed="overlayMode === 'crop'" @click="overlayMode = 'crop'">ROI</button></div></figcaption><img :src="overlayMode === 'overlay' ? selectedFrame.overlay_image : selectedFrame.crop_image" :alt="`帧${selectedFrame.frame}的${overlayMode === 'overlay' ? '实际检测投影' : 'ROI裁切'}`" /><p><strong :class="{ 'unresolved-text': !selectedFrame.accepted }">{{ selectedFrame.accepted ? '几何候选纳入复算' : '未纳入复算，保留未知' }}</strong> · {{ selectedFrame.reason }}</p></figure></div><div class="frame-gate-detail"><div><strong>当前帧实际返回</strong><span>{{ selectedFrame.detections.length }} 个候选 · {{ selectedFrame.inference_ms.toFixed(1) }} ms 推理</span></div><div v-if="selectedFrame.detections.length" class="table-wrapper"><table><caption class="sr-only">当前复核帧候选及几何关联条件</caption><thead><tr><th>候选</th><th>置信度</th><th>前侧 IoU</th><th>后侧 IoU</th><th>区域内</th><th>纳入</th></tr></thead><tbody><tr v-for="(detection, index) in selectedFrame.detections" :key="index"><th>#{{ index + 1 }} {{ detection.label }}</th><td>{{ detection.confidence.toFixed(3) }}</td><td>{{ detection.iou_before.toFixed(3) }}</td><td>{{ detection.iou_after.toFixed(3) }}</td><td>{{ detection.inside_zone ? '是' : '否' }}</td><td>{{ selectedFrame.accepted && selectedFrame.selected_index === index ? '几何候选' : '否' }}</td></tr></tbody></table></div><p>两侧 IoU 门控及歧义排除由程序执行；检测到目标，不自动等于与 T001 同一身份。</p></div></template>
      </section>

      <section ref="agentSection" class="investigation-agent-section" aria-labelledby="investigation-agent-heading"><div class="investigation-agent-context"><h2 id="investigation-agent-heading">把结论交给工具核验，再追问。</h2><p>模型可以先查轨迹缺口，再决定调用局部复核工具；它不会直接读取图片。公开任务清单、工具实际返回与声明核验会随真实执行出现。</p><div class="program-verification" v-if="review?.verification"><h3>该复核记录的程序核验</h3><ul><li v-for="check in review.verification.checks" :key="check.name"><Icon :name="check.passed ? 'check' : 'info'" :size="16" /><div><strong>{{ check.name }} <span>{{ check.passed ? '通过' : '未通过' }}</span></strong><p>{{ check.detail }}</p></div></li></ul><p v-for="limitation in review.verification.limitations" :key="limitation" class="verification-limit">{{ limitation }}</p></div><p v-else class="no-verification-yet">程序核验结果会在本地复核完成后出现。真实 Agent 输出只由右侧模型请求产生。</p><div class="case-version-detail"><details><summary>固定策略与来源版本</summary><dl><div><dt>原视频 SHA256</dt><dd>{{ caseData.source_version }}</dd></div><div><dt>原始索引版本</dt><dd>{{ caseData.scene_version }}</dd></div><div v-if="review?.result"><dt>检测模型 SHA256</dt><dd>{{ review.result.model_sha256 }}</dd></div></dl><pre v-if="review?.result">{{ JSON.stringify(review.result.config, null, 2) }}</pre></details></div></div><AgentPanel ref="agentPanel" :health="modelHealth" :context="chatContext" :suggested-questions="suggestions" @seek="locate" @result="onAgentResult" /></section>
    </template>
  </div>
</template>
