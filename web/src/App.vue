<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from './components/Icon.vue'
import VideoPanel from './components/VideoPanel.vue'
import AgentPanel from './components/AgentPanel.vue'
import PatrolPanel from './components/PatrolPanel.vue'
import EvaluationPage from './components/EvaluationPage.vue'
import AboutPage from './components/AboutPage.vue'
import SourcePage from './components/SourcePage.vue'
import InvestigationPage from './components/InvestigationPage.vue'
import MediaPage from './components/MediaPage.vue'
import ShowcasePage from './components/ShowcasePage.vue'
import DemoPage from './components/DemoPage.vue'
import type { GalleryItem } from './preparedDemos'
import StatisticsSettings from './components/StatisticsSettings.vue'
import { api, errorText } from './api'
import { offlineExamples } from './buildMode'
import { readRoute, sceneHref, resolveSceneId } from './navigation'
import { statisticsFeedback, validStatisticsSeconds } from './statisticsFeedback'
import type { PatrolItem } from './patrol'
import type { Analysis, Health, Scene } from './types'

const firstPage = readRoute(location.hash).page
const page = ref(offlineExamples && !['showcase','demo'].includes(firstPage) ? 'showcase' : firstPage)
const demoId = ref(readRoute(location.hash).sceneId || 'daylight')
const demos = ref<GalleryItem[]>([])
const demoError = ref('')
function onHash() {
  const route = readRoute(location.hash)
  page.value = offlineExamples && !['showcase','demo'].includes(route.page) ? 'showcase' : route.page
  if (route.page === 'demo') demoId.value = route.sceneId || 'daylight'
  window.scrollTo(0, 0)
  if (['experience','evaluation','implementation'].includes(page.value) && !scenes.value.length) void load()
  else if (page.value === 'experience') {
    const id = resolveSceneId(scenes.value, route.sceneId, selectedId.value)
    if (id) void selectScene(id)
  }
}
function openScene(id: string) { location.hash = sceneHref(id) }
function syncSceneRoute(id: string) {
  if (page.value === 'experience' && location.hash !== sceneHref(id)) history.replaceState(null, '', sceneHref(id))
}
function focusMain() { document.getElementById('main-content')?.focus() }
const health = ref<Health | null>(null)
const scenes = ref<Scene[]>([])
const scene = ref<Scene | null>(null)
const analysis = ref<Analysis | null>(null)
const selectedId = ref('')
const zoneId = ref('')
const dwellSeconds = ref(3)
const draftZone = ref('')
const draftDwell = ref<number | string>(3)
const selectedTrackId = ref<string | null>(null)
const currentTime = ref(0)
const initialLoading = ref(true)
const sceneLoading = ref(false)
const analysisLoading = ref(false)
const loadError = ref('')
const analysisError = ref('')
const analysisFeedback = ref('')
const videoPanel = ref<InstanceType<typeof VideoPanel> | null>(null)
const playerSection = ref<HTMLElement | null>(null)
let sceneGeneration = 0
let analysisGeneration = 0
const context = computed(() => ({ scene_id: scene.value?.id || '', zone_id: zoneId.value, dwell_seconds: dwellSeconds.value }))
const validThreshold = computed(() => validStatisticsSeconds(draftDwell.value))

async function loadAnalysis(userTriggered = false) {
  if (!scene.value || !validThreshold.value) return
  const generation = ++analysisGeneration
  const sceneId = scene.value.id
  const requestedZone = draftZone.value
  const requestedDwell = Number(draftDwell.value)
  const previous = analysis.value
  analysisLoading.value = true
  analysisError.value = ''
  analysisFeedback.value = ''
  try {
    const query = new URLSearchParams({ zone_id: requestedZone, dwell_seconds: String(requestedDwell) })
    const result = await api<Analysis>(`/api/scenes/${encodeURIComponent(sceneId)}/analysis?${query}`)
    if (generation !== analysisGeneration || scene.value?.id !== sceneId) return
    analysis.value = result
    zoneId.value = requestedZone
    dwellSeconds.value = requestedDwell
    selectedTrackId.value = null
    if (userTriggered) analysisFeedback.value = statisticsFeedback(scene.value, previous, result)
  } catch (error) { if (generation === analysisGeneration) analysisError.value = errorText(error) }
  finally { if (generation === analysisGeneration) analysisLoading.value = false }
}

async function selectScene(id: string) {
  if (selectedId.value === id && scene.value?.id === id) { syncSceneRoute(id); return }
  const generation = ++sceneGeneration
  analysisGeneration += 1
  selectedId.value = id
  sceneLoading.value = true
  loadError.value = ''
  if (page.value === 'assistant' || page.value === 'investigation') {
    try { health.value = await api<Health>('/api/health') } catch { /* File selection stays available; requests explain any connection failure. */ }
    initialLoading.value = false
    return
  }
  analysis.value = null
  analysisFeedback.value = ''
  selectedTrackId.value = null
  currentTime.value = 0
  try {
    const result = await api<Scene>(`/api/scenes/${encodeURIComponent(id)}`)
    if (generation !== sceneGeneration) return
    scene.value = result
    syncSceneRoute(id)
    zoneId.value = result.default_zone_id
    draftZone.value = result.default_zone_id
    dwellSeconds.value = result.default_dwell_seconds
    draftDwell.value = result.default_dwell_seconds
    await loadAnalysis()
  } catch (error) { if (generation === sceneGeneration) { scene.value = null; loadError.value = errorText(error) } }
  finally { if (generation === sceneGeneration) sceneLoading.value = false }
}

async function load() {
  initialLoading.value = true
  loadError.value = ''
  const [catalogResult, healthResult, demoResult] = await Promise.allSettled([api<{ scenes: Scene[] }>('/api/scenes'), api<Health>('/api/health'),api<{ presets: GalleryItem[] }>('/api/presets')])
  if (demoResult.status === 'fulfilled') { demos.value = demoResult.value.presets; demoError.value = '' }
  else demoError.value = errorText(demoResult.reason)
  if (healthResult.status === 'fulfilled') health.value = healthResult.value
  if (catalogResult.status === 'fulfilled') {
    scenes.value = catalogResult.value.scenes
    if (page.value === 'experience') {
      const id = resolveSceneId(scenes.value, readRoute(location.hash).sceneId, selectedId.value)
      if (id) await selectScene(id)
    }
  } else loadError.value = errorText(catalogResult.reason)
  initialLoading.value = false
}

function seek(t: number, trackId?: string) {
  if (trackId) selectedTrackId.value = trackId
  videoPanel.value?.seek(t)
  playerSection.value?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
}
function playClip(item: PatrolItem) {
  selectedTrackId.value = item.trackId
  void videoPanel.value?.playClip(item.start, item.end, item.name)
  playerSection.value?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
}
function showCurrentRegion() {
  videoPanel.value?.showRegion()
  playerSection.value?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
}
async function viewFailure(sceneId: string, t: number) {
  history.pushState(null, '', sceneHref(sceneId))
  page.value = 'experience'
  await selectScene(sceneId)
  await nextTick()
  seek(t)
  playerSection.value?.scrollIntoView({ block: 'start' })
}
onMounted(() => { window.addEventListener('hashchange', onHash); load() })
onBeforeUnmount(() => { window.removeEventListener('hashchange', onHash); sceneGeneration += 1; analysisGeneration += 1 })
</script>

<template>
  <a class="skip-link" href="#main-content" @click.prevent="focusMain">跳到主要内容</a>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="#showcase" aria-label="视迹 Trace 首页"><span class="brand-symbol"><Icon name="trace" :size="25" /></span><span class="brand-name">视迹 <b>Trace</b></span></a>
      <nav v-if="offlineExamples" aria-label="主导航"><a href="#showcase">项目概览</a><a href="#demo?scene=daylight">三个案例</a></nav>
      <nav v-else aria-label="主导航"><a href="#showcase" :aria-current="page === 'showcase' ? 'page' : undefined">项目概览</a><a href="#assistant" :aria-current="['assistant','demo'].includes(page) ? 'page' : undefined">分析工作台</a><a href="#implementation" :aria-current="!['showcase','assistant','demo'].includes(page) ? 'page' : undefined">项目原理</a></nav>
    </div>
  </header>

  <main id="main-content" tabindex="-1">
    <ShowcasePage v-if="page === 'showcase'" :health="health" :scenes="demos" :loading="initialLoading" :error="demoError" @retry="load" />
    <DemoPage v-else-if="page === 'demo'" :demo-id="demoId" :demos="demos" :health="health" />
    <MediaPage v-else-if="page === 'assistant'" :health="health" />
    <InvestigationPage v-else-if="page === 'investigation'" :health="health" />
    <template v-else-if="page === 'experience'">
      <div class="workbench-intro page-width"><div><h1>视频里发生了什么，<br class="mobile-break" />让证据来回答。</h1><p>选择片段回看，核对事实，再保存带截图的记录。</p></div><div class="live-explainer"><span class="live-symbol"><Icon name="trace" :size="19" /></span><p>围绕当前视频提问<br /><strong>点击回答，回到对应画面</strong></p></div></div>

      <div v-if="initialLoading" class="page-width loading-state" role="status"><span class="spinner"></span>正在载入场景与真实分析数据</div>
      <div v-else-if="loadError" class="page-width page-error" role="alert"><Icon name="info" :size="28" /><h2>场景暂时没有载入</h2><p>{{ loadError }}</p><button class="button primary" @click="load"><Icon name="refresh" :size="16" />重新载入</button></div>
      <div v-else-if="!scenes.length" class="page-width empty-state"><Icon name="film" :size="32" /><h2>尚无可用场景</h2><p>真实视频处理结果准备完成后会显示在这里。</p></div>
      <div v-else class="page-width workbench">
        <div class="scene-strip" role="group" aria-label="选择视频场景">
          <button v-for="(item, index) in scenes" :key="item.id" class="scene-option" :aria-pressed="selectedId === item.id" @click="openScene(item.id)"><span class="scene-order">{{ String(index + 1).padStart(2, '0') }}</span><span><strong>{{ item.title }}</strong><small>{{ item.focus || item.subtitle }}</small></span><Icon name="chevron" :size="17" /></button>
        </div>

        <div v-if="sceneLoading" class="loading-scene" role="status"><span class="spinner"></span>正在载入所选场景</div>
        <template v-if="scene && !sceneLoading">
          <p v-if="scene.data_kind === 'development_fixture'" class="fixture-banner" role="alert">开发样例：本片段含测试 fixture，不能当作真实算法或 Agent 结果。</p>
          <div class="workbench-layout">
            <div ref="playerSection" class="player-column">
              <VideoPanel ref="videoPanel" :scene="scene" :zone-id="zoneId" :analysis-revision="analysis?.review_scope_id" :selected-track-id="selectedTrackId" @time="currentTime = $event" @track="selectedTrackId = $event" />
              <StatisticsSettings :key="scene.id" v-model:zone="draftZone" v-model:seconds="draftDwell" :scene="scene" :analysis="analysis" :loading="analysisLoading" :feedback="analysisFeedback" :error="analysisError" @apply="loadAnalysis(true)" @show-region="showCurrentRegion" />
              <div class="source-line"><span>公开素材 · {{ scene.source.author }}</span><a :href="scene.source.url" target="_blank" rel="noopener noreferrer">来源与许可 <Icon name="link" :size="13" /></a><span class="source-duration">{{ scene.duration.toFixed(1) }} 秒视频</span></div>
            </div>
            <AgentPanel :health="health" :context="context" :scene="scene" :analysis="analysis" @seek="seek" />
          </div>

          <PatrolPanel v-if="analysis" :key="analysis.review_scope_id || `${scene.id}-${zoneId}-${dwellSeconds}`" :scene="scene" :analysis="analysis" :current-time="currentTime" :selected-track-id="selectedTrackId" @seek="seek" @track="selectedTrackId = $event" @clip="playClip" />
        </template>
      </div>
    </template>

    <EvaluationPage v-else-if="page === 'evaluation'" :scenes="scenes" @view="viewFailure" />
    <SourcePage v-else-if="page === 'source'" />
    <AboutPage v-else />
  </main>

  <footer class="site-footer page-width"><span class="footer-brand"><Icon name="trace" :size="16" />视迹 Trace</span><p>观测、工具与证据，可以逐步核对。</p></footer>
</template>
