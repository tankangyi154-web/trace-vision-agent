<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref, toRef, watch } from 'vue'
import Icon from './Icon.vue'
import ClassPicker from './ClassPicker.vue'
import MediaDetectionViewer from './MediaDetectionViewer.vue'
import MediaAnswer from './MediaAnswer.vue'
import { classColor, type MediaTarget } from '../mediaAnnotations'
import { api, ApiError, errorText, timeLabel } from '../api'
import { useChat } from '../composables/useChat'
import { analysisHint, analysisProgress, shouldFollowMessages, isNewReply } from '../mediaWorkspace'
import { mediaLimits, mediaWaitMs, validateMediaFile } from '../mediaPolicy'
import { validMediaScope, type MediaScope } from '../mediaScope'
import { chatStage } from '../plainLanguage'
import { handleChatKeydown } from '../chatKeyboard'
import { readMediaCache, writeMediaCache, saveMediaDraft, readMediaDraft, deleteMediaDraft, isMissingMedia,
  readMediaRecords, rememberMediaRecord, forgetMediaRecord, type MediaReference } from '../mediaPersistence'
import type { Health, Citation } from '../types'
import '../media.css'

type Target = MediaTarget
type Shot = { id: string; t: number; image_url: string; description: string; targetId?: string }
type Result = { kind: 'image' | 'video'; summary: string; class_names: string[]; revision: number; media_url: string; annotation_source_url?: string; poster_url: string; duration: number; width: number; height: number; sample_fps?: number; analysis_scope?: (MediaScope & { partial: boolean; source_duration_seconds: number }) | null; quality?: { low_resolution: boolean; note: string }; targets: Target[]; highlights: Shot[]; counts: { label: string; name: string; count: number; max_simultaneous?: number }[] }
type Job = { id: string; scene_id: string; filename: string; kind: string; classes: number[]; initial_classes: number[]; updating: boolean; status: string; stage: string; phase?: string; elapsed_seconds?: number; can_retry?: boolean; reused_result?: boolean; requested_scope?: MediaScope | null; eta_seconds?: { low: number; high: number } | null; processed: number; total: number; expires_at: number | null; error: string | null; result: Result | null }
type MediaRecord = MediaReference & { scene_id: string; filename: string; kind: string; created_at: number; class_names: string[]; duration: number; target_count: number; poster_url: string }
const savedWorkspace = readMediaCache()
const segmentEnabled = ref(!!savedWorkspace.segment), segmentStart = ref(savedWorkspace.segment?.start_seconds || 0), segmentEnd = ref(savedWorkspace.segment?.end_seconds || 15), sourceDuration = ref(0)
const requestedScope = computed(() => segmentEnabled.value ? { start_seconds: Number(segmentStart.value), end_seconds: Number(segmentEnd.value) } : null)
const scopeValid = computed(() => !requestedScope.value || validMediaScope(requestedScope.value, sourceDuration.value || mediaLimits.video_max_seconds))
let savedJob = savedWorkspace.job
let draftId = savedWorkspace.draftId
let hydrated = false, fileGeneration = 0, restoreGeneration = 0
const restoring = ref(true), restoreError = ref(''), savingDraft = ref(false)
const historyDialog = ref<HTMLDialogElement | null>(null), historyRows = ref<MediaRecord[]>([])
const historyBusy = ref(false), historyError = ref('')
const props = defineProps<{ health: Health | null }>()
const analysisUnavailable = computed(() => {
  const capabilities = props.health?.capabilities
  if (!capabilities) return ''
  if (!capabilities.local_uploads) return '当前环境提供已有案例与回放，本地文件分析尚未开放。'
  if (capabilities.missing?.includes('native_runtime')) return '本机图像分析运行库需要修复。可先查看案例，或运行目录中的“运行环境检查”获取修复说明。'
  if (!capabilities.image_analysis) return '本地识别环境尚未准备好，可以先查看案例演示。'
  if (selectedFile.value && !sourceIsImage.value && !capabilities.video_analysis) return '视频分析环境尚未准备好；你仍可分析图片或查看案例。'
  return ''
})
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const classIds = ref<number[]>(savedWorkspace.classIds)
const classDraftPending = ref(false)
const preview = ref('')
const dragging = ref(false)
const job = ref<Job | null>(null)
const uploading = ref(false)
const error = ref('')
const notice = ref('')
const player = ref<InstanceType<typeof MediaDetectionViewer> | null>(null)
const resultSection = ref<HTMLElement | null>(null)
const messageList = ref<HTMLElement | null>(null)
const previewPlayer = ref<HTMLVideoElement | null>(null)
const mobilePanel = ref<'media' | 'chat'>(savedWorkspace.panel)
const questionComposing = ref(false)
const unreadAnswer = ref(false)
let followConversation = true
let conversationScrollTop = 0
const shotDialog = ref<HTMLDialogElement | null>(null)
const activeShot = ref<Shot | null>(null)
const selectedTarget = ref<string | null>(savedWorkspace.target)
const currentTime = ref(savedWorkspace.time)
const mediaError = ref(false)
const result = computed(() => job.value?.status === 'complete' ? job.value.result : null)
const nextActionHint = computed(() => analysisHint(!!selectedFile.value, classIds.value.length, classDraftPending.value))
const mediaFilename = computed(() => job.value?.filename || selectedFile.value?.name || '')
const sourceIsImage = computed(() => !!selectedFile.value && (selectedFile.value.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(selectedFile.value.name)))
const resultHeadline = computed(() => !result.value?.targets.length ? '没有检出所选物体' : result.value.kind === 'image' ? `识别到${result.value.targets.length}个物体标记` : `识别到${result.value.counts.map(c => c.name).join('、')}`)
const working = computed(() => uploading.value || ['uploading', 'queued', 'running'].includes(job.value?.status || ''))
const canRetrySource = computed(() => !!job.value?.can_retry && classIds.value.length === job.value.classes.length && classIds.value.every(id => job.value!.classes.includes(id)) && JSON.stringify(requestedScope.value) === JSON.stringify(job.value.requested_scope || null))
const context = computed(() => ({ scene_id: result.value ? job.value!.scene_id : '', zone_id: 'A', dwell_seconds: 3, ...(selectedTarget.value ? { selected_target_id: selectedTarget.value } : {}) }))
const chat = useChat(toRef(props, 'health'), context, savedJob?.owner)
const { messages, question, busy: answering, canAsk, connectionError, canRetry, remaining, pending, status: chatStatus } = chat
const suggested = computed(() => {
  const vehicle = result.value?.counts.some(x => ['car', 'bus', 'truck', 'motorcycle'].includes(x.label))
  if (!result.value?.targets.length) return ['再找一下人', '再找一下汽车', '再找一下狗']
  const first = result.value.targets[0]!
  return [vehicle ? '有几辆汽车？' : '识别到了哪些物体？', result.value?.kind === 'video' ? `${first.label_name} #${first.id}什么时候出现？` : '再找一下狗']
})
const highlightedTarget = computed(() => result.value?.targets.find(x => x.id === selectedTarget.value))
let owner = savedJob?.owner || ''
let alive = true
let polling = false
let previewUrl = ''
let expiryTimer: ReturnType<typeof setTimeout> | undefined
let saveTimer: ReturnType<typeof setTimeout> | undefined
function save() {
  if (!alive || !hydrated) return
  writeMediaCache({ job: job.value ? { id: job.value.id, owner } : savedJob, classIds: classIds.value, draftId, ...(requestedScope.value && scopeValid.value ? { segment: requestedScope.value } : {}),
    time: currentTime.value, target: selectedTarget.value, panel: mobilePanel.value })
}
function releaseDraft() { const id = draftId; draftId = null; void deleteMediaDraft(id).catch(() => {}); save() }
function expireMedia(message: string) {
  const id = job.value?.id || savedJob?.id
  if (id) { chat.forgetScene('upload-' + id); forgetMediaRecord(id); historyRows.value = historyRows.value.filter(row => row.id !== id) }
  closeVisuals(); job.value = null; savedJob = null; selectedTarget.value = null; currentTime.value = 0
  selectedFile.value = null; revokePreview(); releaseDraft(); notice.value = message; save()
}
function revokePreview() { if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = ''; preview.value = '' }
function closeVisuals() { player.value?.pause(); previewPlayer.value?.pause(); shotDialog.value?.close(); activeShot.value = null }
function fileSize(size: number) { return size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
async function pickFile(file?: File) {
  if (!file || working.value || answering.value || restoring.value || savingDraft.value) return
  error.value = validateMediaFile(file)
  if (error.value) return
  if (job.value) { try { await newAnalysis() } catch { return } }
  const generation = ++fileGeneration
  releaseDraft()
  selectedFile.value = file
  sourceDuration.value = 0; segmentEnabled.value = false; segmentStart.value = 0; segmentEnd.value = 15
  revokePreview(); previewUrl = URL.createObjectURL(file); preview.value = previewUrl
  savingDraft.value = true
  const id = crypto.randomUUID()
  try {
    await saveMediaDraft(id, file)
    if (!alive || generation !== fileGeneration) { void deleteMediaDraft(id).catch(() => {}); return }
    draftId = id; notice.value = ''; save()
  } catch { if (alive && generation === fileGeneration) notice.value = '浏览器未能暂存文件，刷新后需要重新选择文件；已选物体会保留。' }
  finally { if (generation === fileGeneration) savingDraft.value = false }
}
function change(event: Event) { void pickFile((event.target as HTMLInputElement).files?.[0]) }
function drop(event: DragEvent) { dragging.value = false; void pickFile(event.dataTransfer?.files[0]) }
async function clearJob(keepDraft = false) {
  polling = false
  closeVisuals()
  const previous = job.value ? { id: job.value.id, owner } : savedJob
  if (previous) {
    try { await api(`/api/uploads/${previous.id}`, { method: 'DELETE', headers: { 'X-Session-ID': previous.owner } }) }
    catch (e) { if (!(e instanceof ApiError && e.status === 404)) { error.value = '清理上一份素材未完成，请稍后再试。'; throw e } }
    chat.forgetScene('upload-' + previous.id); forgetMediaRecord(previous.id)
    historyRows.value = historyRows.value.filter(row => row.id !== previous.id)
  }
  job.value = null; savedJob = null; selectedTarget.value = null; currentTime.value = 0; mediaError.value = false; unreadAnswer.value = false; followConversation = true; conversationScrollTop = 0; mobilePanel.value = 'media'
  if (!keepDraft) releaseDraft()
  save()
}
async function newAnalysis() {
  if (job.value && job.value.status !== 'complete') await clearJob()
  polling = false; closeVisuals(); ++fileGeneration; restoreGeneration++
  job.value = null; savedJob = null; selectedFile.value = null; selectedTarget.value = null; currentTime.value = 0
  mobilePanel.value = 'media'; unreadAnswer.value = false; followConversation = true; mediaError.value = false
  segmentEnabled.value = false; segmentStart.value = 0; segmentEnd.value = 15; sourceDuration.value = 0
  releaseDraft(); revokePreview(); error.value = ''; notice.value = ''; save()
  if (fileInput.value) fileInput.value.value = ''
}
async function reset() {
  try { await clearJob(); selectedFile.value = null; revokePreview(); error.value = ''; notice.value = ''; if (fileInput.value) fileInput.value.value = '' }
  catch { /* Keep current analysis if cleanup could not be confirmed. */ }
}
async function follow(id: string) {
  polling = true
  const deadline = Date.now() + mediaWaitMs
  while (alive && polling && job.value?.id === id) {
    await new Promise(resolve => setTimeout(resolve, 700))
    if (!alive || !polling || job.value?.id !== id) return
    try {
      const next = await api<Job>(`/api/uploads/${id}`, { headers: { 'X-Session-ID': owner } })
      if (!alive || job.value?.id !== id) return
      job.value = next; save()
      if (next.status === 'complete' || next.status === 'failed') {
        polling = false
        if (next.status === 'complete') mobilePanel.value = 'media'
        return
      }
    } catch (e) {
      polling = false
      if (isMissingMedia(e)) expireMedia('这份分析已删除或未完成，请重新选择文件。')
      else error.value = errorText(e)
      return
    }
    if (Date.now() > deadline) { polling = false; error.value = '这份文件还没处理完。点击“重新连接”查询已有分析。'; return }
  }
}
async function start() {
  if (working.value || answering.value || savingDraft.value || !classIds.value.length || classDraftPending.value || !scopeValid.value || (!selectedFile.value && !canRetrySource.value)) return
  if (canRetrySource.value && job.value) {
    uploading.value = true; error.value = ''; notice.value = ''
    try {
      const next = await api<Job>(`/api/uploads/${job.value.id}/retry`, { method: 'POST', headers: { 'X-Session-ID': owner } })
      job.value = next; save(); void follow(next.id)
    } catch (e) { error.value = errorText(e) }
    finally { uploading.value = false }
    return
  }
  const requestedClasses = [...classIds.value]
  previewPlayer.value?.pause()
  uploading.value = true; error.value = ''; notice.value = ''
  try {
    owner = await chat.ensureSession()
    await clearJob(true)
    chat.setMediaOwner(owner)
    let next: Job
    const submit = async () => {
      const file = selectedFile.value!
      return api<Job>('/api/uploads', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Session-ID': owner, 'X-Filename': encodeURIComponent(file.name), 'X-File-Size': String(file.size), 'X-Target-Classes': JSON.stringify(requestedClasses), 'X-Analysis-Scope': JSON.stringify(requestedScope.value) }, body: file })
    }
    try { next = await submit() }
    catch (e) { if (!(e instanceof ApiError && e.code === 'session_not_found')) throw e; owner = await chat.ensureSession(true); next = await submit() }
    if (!alive) return
    job.value = next; savedJob = { id: next.id, owner }; save(); void follow(next.id)
  } catch (e) { error.value = errorText(e) }
  finally { uploading.value = false }
}
function seek(t: number) { mobilePanel.value = 'media'; currentTime.value = t; player.value?.seek(t); void nextTick(() => resultSection.value?.scrollIntoView({ block: 'nearest' })) }
function selectTarget(target: Target) { selectedTarget.value = target.id; if (result.value?.kind === 'video') seek(target.first_seen) }
async function showShot(shot: Shot) { activeShot.value = shot; await nextTick(); shotDialog.value?.showModal() }
function showCitation(citation: Citation) {
  const target = result.value?.targets.find(item => item.id === citation.track_id)
  void showShot({ id: citation.evidence_id, t: citation.t, image_url: citation.image_url, targetId: target?.id, description: target ? `${target.name}的回答依据` : '回答引用的实际画面' })
}
function replayShot() {
  if (!activeShot.value) return
  selectedTarget.value = activeShot.value.targetId || null
  seek(activeShot.value.t); shotDialog.value?.close()
}
async function send(value?: string) {
  if (!canAsk.value || !(value ?? question.value).trim()) return
  mobilePanel.value = 'chat'; unreadAnswer.value = false; followConversation = true
  void nextTick(scrollConversation)
  await chat.send(value)
}
function questionKeydown(event: KeyboardEvent) { handleChatKeydown(event, () => send(), questionComposing.value) }
function scrollConversation() { if (messageList.value) { messageList.value.scrollTop = messageList.value.scrollHeight; conversationScrollTop = messageList.value.scrollTop } }
function onConversationScroll() { if (messageList.value?.offsetParent) { conversationScrollTop = messageList.value.scrollTop; followConversation = shouldFollowMessages(messageList.value); if (followConversation) unreadAnswer.value = false } }
function showNewAnswer() { followConversation = true; unreadAnswer.value = false; scrollConversation() }
function switchPanel(panel: 'media' | 'chat') {
  if (panel === mobilePanel.value) return
  if (messageList.value?.offsetParent) conversationScrollTop = messageList.value.scrollTop
  mobilePanel.value = panel
  if (panel === 'chat') {
    player.value?.pause()
    void nextTick(() => { if (followConversation) { scrollConversation(); unreadAnswer.value = false } else if (messageList.value) messageList.value.scrollTop = conversationScrollTop })
  }
}
watch([() => messages.value.length, () => messages.value.at(-1)?.result?.answer, answering, () => messages.value.at(-1)?.id], async ([, answer, , id], old) => {
  await nextTick()
  const hiddenOnMobile = mobilePanel.value !== 'chat' && window.matchMedia('(max-width: 900px)').matches
  if (followConversation && !hiddenOnMobile) scrollConversation()
  else if (isNewReply({ id, answer }, { id: old?.[3], answer: old?.[1] })) unreadAnswer.value = true
})
async function restoreWorkspace() {
  const generation = ++restoreGeneration
  restoring.value = true; restoreError.value = ''; hydrated = false
  try {
    if (savedJob) {
      owner = savedJob.owner; chat.setMediaOwner(owner)
      const restored = await api<Job>(`/api/uploads/${savedJob.id}`, { headers: { 'X-Session-ID': owner } })
      if (!alive || generation !== restoreGeneration) return
      job.value = restored
      if (savedWorkspace.job?.id !== restored.id || restored.status === 'complete') {
        classIds.value = restored.initial_classes || restored.classes?.slice(0, 3) || []
        segmentEnabled.value = !!restored.requested_scope
        segmentStart.value = restored.requested_scope?.start_seconds || 0
        segmentEnd.value = restored.requested_scope?.end_seconds || 15
      }
      if (selectedTarget.value && !restored.result?.targets.some(target => target.id === selectedTarget.value)) selectedTarget.value = null
      if (['queued', 'running'].includes(restored.status)) void follow(restored.id)
    }
    if (draftId && job.value?.status !== 'complete') {
      const file = await readMediaDraft(draftId)
      if (!alive || generation !== restoreGeneration) return
      if (file) { selectedFile.value = file; revokePreview(); previewUrl = URL.createObjectURL(file); preview.value = previewUrl }
      else { draftId = null; notice.value = '待分析文件的暂存已到期，请重新选择文件；已选物体仍然保留。' }
    }
  } catch (e) {
    if (!alive || generation !== restoreGeneration) return
    if (isMissingMedia(e)) expireMedia('这份分析已删除或未完成，请重新选择文件。')
    else restoreError.value = '暂时未能恢复上次的工作，记录已保留，请重新连接。'
  } finally {
    if (alive && generation === restoreGeneration) { restoring.value = false; hydrated = true; save() }
  }
}
async function openHistory() {
  historyDialog.value?.showModal(); historyBusy.value = true; historyError.value = ''
  try {
    const currentOwner = await chat.ensureSession()
    const owners = [...new Set([currentOwner, owner, ...readMediaRecords().map(row => row.owner)].filter(Boolean))]
    const responses = await Promise.allSettled(owners.map(async recordOwner => {
      const response = await api<{ records: Omit<MediaRecord, 'owner'>[] }>('/api/uploads', { headers: { 'X-Session-ID': recordOwner } })
      return response.records.map(record => ({ ...record, owner: recordOwner }))
    }))
    if (!alive) return
    const rows = responses.flatMap(response => response.status === 'fulfilled' ? response.value : [])
    historyRows.value = rows.sort((a, b) => b.created_at - a.created_at)
    rows.forEach(rememberMediaRecord)
    if (responses.some(response => response.status === 'rejected')) historyError.value = '部分记录暂时未能读取，请重新连接后重试。'
  } catch { historyError.value = '暂时无法读取本机记录，请重新连接后重试。' }
  finally { historyBusy.value = false }
}
async function switchRecord(record: MediaRecord) {
  if (working.value || answering.value || pending.value) return
  save(); closeVisuals(); releaseDraft(); revokePreview(); selectedFile.value = null
  savedJob = { id: record.id, owner: record.owner }; owner = record.owner; chat.setMediaOwner(owner)
  job.value = null; selectedTarget.value = null; currentTime.value = 0; mobilePanel.value = 'media'; mediaError.value = false
  notice.value = ''; error.value = ''; historyDialog.value?.close()
  save()
  await restoreWorkspace()
}
async function deleteRecord(record: MediaRecord) {
  try {
    if (job.value?.id === record.id || savedJob?.id === record.id) await reset()
    else {
      await api(`/api/uploads/${record.id}`, { method: 'DELETE', headers: { 'X-Session-ID': record.owner } })
      chat.forgetScene(record.scene_id); forgetMediaRecord(record.id)
    }
    if (job.value?.id === record.id || savedJob?.id === record.id) throw new Error('Record was not deleted')
    historyRows.value = historyRows.value.filter(row => row.id !== record.id)
  } catch { historyError.value = '删除未完成，记录已保留，请重试。' }
}
onMounted(() => {
  window.addEventListener('pagehide', save)
  void restoreWorkspace()
})
watch(() => messages.value.at(-1)?.result, async value => {
  if (!value || !['complete', 'failed'].includes(value.status) || !job.value || !owner) return
  const id = job.value.id
  try { const next = await api<Job>(`/api/uploads/${id}`, { headers: { 'X-Session-ID': owner } }); if (alive && job.value?.id === id) { job.value = next; save() } } catch { /* The chat retains its exact request outcome; expiry controls clear old results. */ }
})
watch(chat.expiredScene, sceneId => { if (job.value?.scene_id === sceneId) expireMedia('这份分析已删除，请选择其他识别记录或新文件。') })
watch(() => `${job.value?.id}:${job.value?.status}`, () => {
  if (job.value?.status === 'complete') { savedJob = { id: job.value.id, owner }; rememberMediaRecord(savedJob); releaseDraft(); selectedFile.value = null; revokePreview(); save() }
})
watch([classIds, selectedTarget, currentTime, mobilePanel], () => {
  if (!hydrated) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(save, 200)
}, { deep: true })
watch([segmentEnabled, segmentStart, segmentEnd], save)
function previewMetadata(event: Event) {
  const duration = (event.target as HTMLVideoElement).duration
  sourceDuration.value = Number.isFinite(duration) ? duration : 0
  if (!segmentEnabled.value && duration > 0) segmentEnd.value = Math.min(15, Math.floor(duration * 10) / 10)
}
watch(() => job.value?.expires_at, expires => {
  if (expiryTimer) clearTimeout(expiryTimer)
  if (!expires) return
  expiryTimer = setTimeout(() => { void restoreWorkspace() }, Math.max(1000, expires * 1000 - Date.now()))
})
onScopeDispose(() => { save(); alive = false; ++fileGeneration; restoreGeneration++; polling = false; if (saveTimer) clearTimeout(saveTimer); if (expiryTimer) clearTimeout(expiryTimer); window.removeEventListener('pagehide', save); revokePreview() })
</script>

<template>
  <div class="media-page" :class="{ 'has-result': result }">
    <header class="workspace-heading">
      <div><p class="workspace-eyebrow">视迹 / 图片与短视频</p><h1>视觉分析工作台</h1><p class="workspace-subtitle">上传素材，找到你关心的物体，再继续提问。</p></div>
      <div class="workspace-actions"><button class="media-secondary" :disabled="working || answering || !!pending || restoring || savingDraft" @click="openHistory">识别记录</button><button v-if="result" class="media-secondary" :disabled="answering || !!pending" @click="newAnalysis"><Icon name="upload" :size="16" />分析新素材</button></div>
    </header>
    <section v-if="restoring || restoreError" class="media-recovery" role="status" aria-live="polite"><h2>{{ restoring ? '正在恢复上次的工作…' : '上次的工作还在' }}</h2><p>{{ restoreError || '正在读取文件、识别结果和已选物体。' }}</p><button v-if="restoreError" class="media-primary" @click="restoreWorkspace">重新连接</button></section>
    <p v-if="!restoring && !restoreError && !result && analysisUnavailable" class="media-notice" role="status">{{ analysisUnavailable }} <a href="#showcase">查看案例与运行记录</a></p>
    <div v-if="result && !restoring && !restoreError" class="workspace-mobile-tabs" role="tablist" aria-label="工作区">
      <button id="tab-media" role="tab" aria-controls="media-visual-panel" :aria-selected="mobilePanel === 'media'" @click="switchPanel('media')">画面与目标</button>
      <button id="tab-chat" role="tab" aria-controls="media-chat-panel" :aria-selected="mobilePanel === 'chat'" @click="switchPanel('chat')">结果与问答<span v-if="unreadAnswer" class="unread-dot" aria-label="有新回答"></span></button>
    </div>
    <div v-if="!restoring && !restoreError" ref="resultSection" class="workspace-shell" :class="{ 'has-result': result }" :data-mobile-pane="mobilePanel">
      <section id="media-visual-panel" class="workspace-media-panel" aria-label="素材画面、目标和证据">
        <header class="workspace-media-toolbar"><div><h2>{{ mediaFilename || '上传素材' }}</h2><p v-if="selectedFile && !result">{{ fileSize(selectedFile.size) }}</p><p v-else-if="result">{{ result.kind === 'video' ? '视频 · 点击目标或截图回看' : '图片 · 点击目标高亮' }}</p><p v-else>第一步 · 选择一张图片或一段短视频</p></div><span class="workspace-phase" :class="{ complete: result, running: working }">{{ result ? '分析完成' : working ? '正在分析' : selectedFile ? '已选文件' : '等待上传' }}</span></header>
        <input ref="fileInput" class="sr-only" tabindex="-1" aria-hidden="true" type="file" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm" :disabled="working || answering" @change="change" />
        <div class="workspace-media-stage" :class="{ dragging, 'has-media': selectedFile || result }" @dragover.prevent="!working && !answering && (dragging = true)" @dragleave.prevent="dragging = false" @drop.prevent="drop">
          <MediaDetectionViewer v-if="result" ref="player" :result="result" :selected-target="selectedTarget" :initial-time="currentTime" @time="currentTime = $event" @error="mediaError = true" />
          <template v-else-if="selectedFile"><img v-if="sourceIsImage" class="media-source-preview" :src="preview" alt="已选择的图片预览" /><video v-else ref="previewPlayer" class="media-source-preview" :src="preview" controls playsinline preload="metadata" aria-label="已选择的视频预览" @loadedmetadata="previewMetadata"></video></template>
          <button v-else class="file-drop-button" :disabled="working" @click="fileInput?.click()"><span class="upload-symbol"><Icon name="upload" :size="26" /></span><strong>上传图片或短视频</strong><span>拖放文件到这里，或<span class="file-pick-link">选择文件</span></span></button>
          <div v-if="working" class="media-working-overlay" aria-hidden="true"><span class="media-loader"></span><span>{{ uploading ? (canRetrySource ? '正在重试当前素材…' : '正在上传素材…') : job?.stage || '正在准备分析…' }}</span></div>
        </div>
        <div v-if="!result" class="workspace-file-footer"><p>图片 JPG / PNG / WebP · 最多{{ mediaLimits.image_max_mb }}MB<br />视频 MP4 / MOV / WebM · 最长{{ mediaLimits.video_max_seconds / 60 }}分钟、最多{{ mediaLimits.video_max_mb }}MB</p><button v-if="selectedFile && !working" class="media-link" :disabled="savingDraft" @click="fileInput?.click()">更换文件</button></div>
        <template v-else>
          <p v-if="job?.reused_result" class="media-notice media-inline-status" role="status">已找到本机相同素材与相同配置的结果，直接打开，无需重新识别。</p>
          <p v-if="result.analysis_scope?.partial" class="media-scope-banner" role="status">本次仅分析原视频 {{timeLabel(result.analysis_scope.start_seconds)}}—{{timeLabel(result.analysis_scope.end_seconds)}}。以下时刻从所选片段起点计。</p>
          <p v-if="mediaError" class="media-error-text media-inline-status" role="alert">标注视频暂时无法播放，可先查看下方截图，或重新分析。</p>
          <div v-if="result.targets.length" class="media-targets"><div class="media-section-label"><h2>识别到的物体</h2><span>点击单独查看{{ result.kind === 'video' ? '并定位' : '' }}</span></div><div class="media-target-list"><button v-for="target in result.targets.slice(0, 6)" :key="target.id" :aria-pressed="selectedTarget === target.id" @click="selectTarget(target)"><i class="media-type-dot" :style="{ background: classColor(target.label) }"></i><span>{{ target.label_name }}</span>#{{ target.id }}</button><details v-if="result.targets.length > 6"><summary>其余{{ result.targets.length - 6 }}个标记</summary><div><button v-for="target in result.targets.slice(6)" :key="target.id" :aria-pressed="selectedTarget === target.id" @click="selectTarget(target)"><i class="media-type-dot" :style="{ background: classColor(target.label) }"></i><span>{{ target.label_name }}</span>#{{ target.id }}</button></div></details></div><p v-if="highlightedTarget" class="media-target-caption">正在查看{{ highlightedTarget.label_name }} #{{ highlightedTarget.id }}<span v-if="result.kind === 'video'">，首次识别于{{ highlightedTarget.first_seen }}秒</span>。可在画面下方取消“只看选中的物体”。</p></div>
          <section v-if="result.kind === 'video' && result.highlights.length" class="media-highlights" aria-labelledby="highlights-title"><div class="media-section-label"><h2 id="highlights-title">关键画面</h2><span>点开查看，或回到视频</span></div><div><button v-for="shot in result.highlights" :key="shot.id" @click="showShot(shot)"><img :src="shot.image_url" :alt="shot.description" width="240" height="135" loading="lazy" /><span>{{ timeLabel(shot.t) }}</span><p>{{ shot.description }}</p></button></div></section>
          <div class="media-result-footnote"><p>{{ result.kind === 'video' ? '编号仅用于这段视频。遮挡后无法确认是同一物体时，会重新编号。' : '识别结果可能有遗漏或出错，建议结合画面核对。' }}</p><a :href="result.media_url" download><Icon name="download" :size="15" />保存标注{{ result.kind === 'video' ? '视频' : '图片' }}</a></div>
        </template>
      </section>
      <aside v-if="!result" class="workspace-setup" aria-label="识别目标和开始分析">
        <p class="workspace-step">第二步 · 指定物体</p>
        <ClassPicker v-if="!working" v-model="classIds" :disabled="!selectedFile || answering" @pending-change="classDraftPending = $event" />
        <details v-if="selectedFile && !sourceIsImage && !working" class="media-range"><summary>分析范围：{{segmentEnabled ? '选择时间片段' : '完整视频'}}</summary><label class="media-range-toggle"><input v-model="segmentEnabled" type="checkbox" />只分析指定时间片段</label><div class="media-range-fields"><label>开始（秒）<input v-model.number="segmentStart" type="number" min="0" :max="sourceDuration || mediaLimits.video_max_seconds" step="0.1" :disabled="!segmentEnabled" /></label><label>结束（秒）<input v-model.number="segmentEnd" type="number" min="0.1" :max="sourceDuration || mediaLimits.video_max_seconds" step="0.1" :disabled="!segmentEnabled" /></label></div><p>默认分析完整视频。选择片段后仅处理所选范围，结果会标明范围与时间起点。</p><p v-if="!scopeValid" class="media-error-text" role="alert">结束时间应晚于开始时间，且不能超出视频长度。</p></details>
        <div v-if="working" class="media-working" role="status" aria-live="polite"><h2>{{ uploading ? (canRetrySource ? '正在重试当前素材' : '正在上传你的文件') : job?.stage }}</h2><progress v-if="job?.total && job.phase === 'detecting'" aria-label="画面识别进度" :max="job.total" :value="job.processed"></progress><progress v-else aria-label="文件分析进度"></progress><p>{{ job ? analysisProgress(job) : '正在接收文件，请稍等。' }}</p><button v-if="job" class="media-link" @click="reset">取消分析</button></div>
        <template v-else><div class="workspace-start"><p id="analysis-hint" class="workspace-next-step">{{ savingDraft ? '正在保留文件，刷新后可以继续…' : canRetrySource ? '素材已暂存，可以直接重试，无需重新上传。' : nextActionHint || '准备好了，可以开始分析。' }}</p><button class="media-primary" :disabled="(!selectedFile && !canRetrySource) || !classIds.length || classDraftPending || !scopeValid || savingDraft || !!analysisUnavailable" aria-describedby="analysis-hint" @click="start()">{{ job?.status === 'failed' ? '重试当前素材' : '开始分析' }}<Icon name="arrow" :size="17" /></button></div><p class="workspace-setup-note">分析后可直接提问，继续补找其他物体。</p></template>
        <p v-if="job?.status === 'failed'" class="media-error-text" role="alert">{{ job.error }}</p>
        <p v-if="error" class="media-error-text" role="alert">{{ error }}<button v-if="job && !polling" class="media-link" @click="follow(job.id)">重新连接</button></p>
        <p v-if="notice" class="media-notice" role="status">{{ notice }}</p>
      </aside>
      <aside v-else id="media-chat-panel" class="media-conversation" aria-label="识别结果与素材问答">
        <div class="media-summary"><h2>识别结果</h2><p class="media-summary-headline">{{ resultHeadline }}</p><div v-if="result.counts.length" class="media-counts"><span v-for="row in result.counts" :key="row.label">{{ row.name }}<b>{{ result.kind === 'video' ? `最多 ${row.max_simultaneous ?? row.count}` : row.count }}</b></span></div><p class="media-searched-scope">已查找：{{ result.class_names?.join('、') }}</p></div>
        <div class="media-chat-heading"><h2>继续提问</h2><span>{{ highlightedTarget ? `已选中${highlightedTarget.name}` : '围绕当前素材' }}</span></div>
        <p v-if="!health?.live_agent" class="media-notice">暂时无法继续提问，你仍可查看识别结果和标注画面。</p>
        <div v-else class="media-question-suggestions"><button v-for="item in suggested.slice(0, 2)" :key="item" :disabled="!canAsk" @click="send(item)">{{ item }}</button></div>
        <div ref="messageList" class="media-chat-messages" role="log" aria-label="素材对话" aria-live="polite" @scroll="onConversationScroll">
          <p v-if="!messages.length" class="media-chat-empty">可以问数量、出现时间，或说“再找一下卡车”。</p>
          <article v-for="message in messages" :key="message.id"><p class="media-user-question">{{ message.question }}</p><MediaAnswer v-if="message.result?.answer" :reply="message.result" :targets="result.targets" :kind="result.kind" @citation="showCitation" /><p v-if="message.result?.error || message.error" class="media-error-text" role="alert">{{ message.result?.error?.message || '这次提问没有完成，请稍后再试。' }}</p></article>
          <p v-if="answering" class="media-answering" role="status"><span class="spinner"></span>{{ chatStage(chatStatus) }}</p>
        </div>
        <button v-if="unreadAnswer" class="media-new-answer" @click="showNewAnswer">查看新回答 ↓</button>
        <p v-if="connectionError && !answering" class="media-error-text media-inline-status" role="alert">{{ connectionError }}</p><button v-if="canRetry" class="media-link media-reconnect" @click="chat.reconnect">恢复上一条提问</button><p v-if="remaining === 0" class="media-notice media-inline-status">本次可用提问次数已用完，可以继续查看已有结果。</p>
        <form class="media-chat-form" @submit.prevent="send()"><label for="media-question">继续问这份素材</label><div class="media-composer"><textarea id="media-question" v-model="question" :disabled="!canAsk" rows="2" maxlength="500" aria-describedby="media-question-help" placeholder="问数量、出现时间，或补找物体…" @compositionstart="questionComposing = true" @compositionend="questionComposing = false" @keydown="questionKeydown"></textarea><button class="media-send-button" :disabled="!canAsk || !question.trim()" type="submit" :aria-label="answering ? '正在回答' : '发送问题'" :title="answering ? '正在回答' : '发送问题'"><Icon name="arrow" :size="19" /></button></div><p id="media-question-help">Enter 发送 · Shift + Enter 换行</p></form>
      </aside>
    </div>
    <div v-if="result && !restoring && !restoreError" class="media-delete-row"><span>已保存到本机识别记录，可随时切换查看</span><button class="media-link media-delete" :disabled="answering || !!pending" @click="reset">删除这份素材和分析</button></div>
    <p class="media-privacy">素材与识别记录保存在本机，手动删除后移除。提问时发送相关识别信息，询问外观或动作时额外发送选中物体的少量截图。</p>
    <dialog ref="historyDialog" class="media-history-dialog" aria-labelledby="media-history-title" @click="($event.target === historyDialog) && historyDialog?.close()"><header><div><h2 id="media-history-title">本机识别记录</h2><p>直接查看已有结果，不会重新识别。</p></div><button class="media-icon-button" aria-label="关闭识别记录" @click="historyDialog?.close()"><Icon name="close" /></button></header><p v-if="historyBusy" class="media-notice" role="status">正在读取识别记录…</p><p v-if="historyError" class="media-error-text" role="alert">{{ historyError }}<button class="media-link" :disabled="historyBusy" @click="openHistory">重试</button></p><p v-if="!historyBusy && !historyError && !historyRows.length" class="media-notice">还没有识别记录。分析完成后会自动保存在这里。</p><ul class="media-record-list"><li v-for="record in historyRows" :key="record.id"><img :src="record.poster_url" alt="" width="120" height="90" loading="lazy" /><div class="media-record-info"><h3>{{ record.filename }}</h3><p>{{ record.kind === 'video' ? '视频' : '图片' }} · {{ record.class_names.join('、') }}</p><time :datetime="new Date(record.created_at * 1000).toISOString()">{{ new Date(record.created_at * 1000).toLocaleString('zh-CN') }}</time></div><div class="media-record-actions"><button class="media-secondary" :aria-label="`查看${record.filename}`" :disabled="historyBusy" @click="switchRecord(record)">{{ record.id === job?.id ? '继续查看' : '查看' }}</button><button class="media-link media-delete" :aria-label="`删除${record.filename}`" :disabled="historyBusy" @click="deleteRecord(record)">删除</button></div></li></ul></dialog>
    <dialog ref="shotDialog" class="media-shot-dialog" aria-labelledby="shot-title" @click="($event.target === shotDialog) && shotDialog?.close()"><template v-if="activeShot"><header><h2 id="shot-title">{{ activeShot.description }}</h2><button class="media-icon-button" aria-label="关闭截图" @click="shotDialog?.close()"><Icon name="close" /></button></header><img :src="activeShot.image_url" :alt="activeShot.description" /><button v-if="result?.kind === 'video'" class="media-primary" @click="replayShot">在视频中回看这一刻</button></template></dialog>
  </div>
</template>
