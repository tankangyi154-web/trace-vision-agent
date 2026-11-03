<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './Icon.vue'
import { timeLabel } from '../api'
import { targetName } from '../plainLanguage'
import { demoPoster } from '../demoPosters'
import { clipRange, observedTrajectories, sampleAtTime } from '../patrol'
import type { Scene, Track } from '../types'

const props = defineProps<{ scene: Scene; zoneId: string; selectedTrackId: string | null; analysisRevision?: string }>()
const emit = defineEmits<{ time: [t: number]; track: [id: string | null] }>()
const player = ref<HTMLVideoElement | null>(null)
const mode = ref<'annotated' | 'original'>('annotated')
const currentTime = ref(0)
const showZone = ref(false)
const mediaError = ref(false)
const activeClip = ref<{ start: number; end: number; title: string } | null>(null)
const clipFinished = ref(false)
const clipNotice = ref('')
let clipGeneration = 0
let playbackFrame: number | undefined
let restoreTime = 0
let restorePlaying = false
const src = computed(() => mode.value === 'annotated' ? props.scene.annotated_url : props.scene.original_url)
const zone = computed(() => props.scene.zones.find((item) => item.id === props.zoneId))
const polygon = computed(() => zone.value?.polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' '))
const track = computed<Track | undefined>(() => props.scene.tracks?.find((item) => item.id === props.selectedTrackId))
const trajectories = computed(() => observedTrajectories(track.value, sceneSamplingFps.value, activeClip.value))
const sceneSamplingFps = computed(() => Number(props.scene.processing.sample_fps) || props.scene.fps)
const nearestSample = computed(() => sampleAtTime(track.value, currentTime.value, props.scene.fps))

function stopWatch() { if (playbackFrame !== undefined) cancelAnimationFrame(playbackFrame); playbackFrame = undefined }
function cancelClip() { stopWatch(); clipGeneration++; activeClip.value = null; clipFinished.value = false; clipNotice.value = '' }
function stopAtClipEnd() {
  if (!activeClip.value || !player.value || player.value.currentTime < activeClip.value.end - .005) return false
  player.value.pause()
  if (Math.abs(player.value.currentTime - activeClip.value.end) > .001) player.value.currentTime = activeClip.value.end
  currentTime.value = activeClip.value.end; emit('time', currentTime.value)
  clipFinished.value = true; stopWatch()
  return true
}
function onPlay() {
  if (activeClip.value && player.value) {
    if (player.value.currentTime >= activeClip.value.end - .005) player.value.currentTime = activeClip.value.start
    clipFinished.value = false; clipNotice.value = ''
  }
  stopWatch()
  const tick = () => {
    if (!player.value || player.value.paused || stopAtClipEnd()) return
    const t = player.value.currentTime
    if (Math.floor(t * props.scene.fps) !== Math.floor(currentTime.value * props.scene.fps)) currentTime.value = t
    playbackFrame = requestAnimationFrame(tick)
  }
  playbackFrame = requestAnimationFrame(tick)
}
function onSeeking() {
  if (activeClip.value && player.value && (player.value.currentTime < activeClip.value.start - .1 || player.value.currentTime > activeClip.value.end + .1)) cancelClip()
}
function updateTime() { if (stopAtClipEnd()) return; currentTime.value = player.value?.currentTime || 0; emit('time', currentTime.value) }
function seek(t: number) {
  cancelClip(); player.value?.pause()
  const target = Math.max(0, Math.min(t, props.scene.duration))
  restoreTime = target
  if (player.value && player.value.readyState >= 1) player.value.currentTime = target
  currentTime.value = target
  emit('time', target)
}
async function playClip(start: number, end: number, title: string) {
  const range = clipRange(start, end, props.scene.duration)
  if (!range) return
  seek(range.start)
  activeClip.value = { ...range, title }
  const generation = clipGeneration
  await nextTick()
  try { await player.value?.play() }
  catch { if (generation === clipGeneration && activeClip.value) clipNotice.value = '片段已定位，请点击视频播放。' }
}
async function switchMode(value: 'annotated' | 'original') {
  if (mode.value === value) return
  restoreTime = player.value?.currentTime || 0
  restorePlaying = !!player.value && !player.value.paused
  mode.value = value
  mediaError.value = false
  await nextTick()
  player.value?.load()
}
function restore() {
  if (!player.value) return
  player.value.currentTime = Math.min(restoreTime, props.scene.duration)
  if (restorePlaying) player.value.play().catch(() => { /* Browser may require another user gesture. */ })
  restorePlaying = false
}
watch(() => props.scene.id, () => { cancelClip(); restoreTime = 0; restorePlaying = false; currentTime.value = 0; mediaError.value = false; showZone.value = false })
watch(() => props.analysisRevision, () => { if (activeClip.value) { player.value?.pause(); cancelClip() } })
onBeforeUnmount(cancelClip)
function showRegion() { showZone.value = true }
defineExpose({ seek, showRegion, playClip })
</script>

<template>
  <section class="video-panel" aria-label="视频播放器与轨迹">
    <div class="video-toolbar">
      <div class="video-caption"><Icon name="film" :size="17" /><span>{{ scene.title }}</span></div>
      <div class="segmented" role="group" aria-label="视频显示模式">
        <button :aria-pressed="mode === 'original'" @click="switchMode('original')">原始视频</button>
        <button :aria-pressed="mode === 'annotated'" @click="switchMode('annotated')">识别标记</button>
      </div>
    </div>
    <div class="video-stage" :style="{ aspectRatio: `${scene.width} / ${scene.height}` }">
      <video ref="player" :key="scene.id" :src="src" :poster="demoPoster(scene.id, scene.poster_url)" controls playsinline preload="metadata" @timeupdate="updateTime" @loadedmetadata="restore" @play="onPlay" @pause="stopWatch" @seeking="onSeeking" @error="mediaError = true" :aria-label="`${scene.title}，${mode === 'original' ? '原始' : '识别标记'}视频`"></video>
      <svg class="video-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
        <polygon v-if="showZone && polygon" :points="polygon" fill="rgba(65,123,255,.12)" stroke="#83A8FF" stroke-width="3" stroke-dasharray="10 7" />
        <polyline v-for="(trajectory, index) in trajectories" :key="index" :points="trajectory" fill="none" stroke="#FFCA7A" stroke-width="4" />
        <rect v-if="nearestSample" :x="nearestSample.bbox[0] * 1000" :y="nearestSample.bbox[1] * 1000" :width="(nearestSample.bbox[2] - nearestSample.bbox[0]) * 1000" :height="(nearestSample.bbox[3] - nearestSample.bbox[1]) * 1000" fill="none" stroke="#FFCA7A" stroke-width="4" />
      </svg>
      <span v-if="showZone && zone" class="zone-label">统计范围 · {{ zone.name || `区域 ${zone.id}` }}</span>
      <span v-if="selectedTrackId" class="track-overlay-label">{{ targetName(selectedTrackId, track?.label) }}的识别位置</span>
      <div v-if="mediaError" class="media-error" role="alert"><Icon name="info" :size="24" /><p>视频加载失败</p><button class="button secondary" @click="player?.load(); mediaError = false">重新加载视频</button></div>
    </div>
    <div class="video-status"><span class="time-display">{{ timeLabel(currentTime) }} <span>/ {{ timeLabel(scene.duration) }}</span></span><button class="text-button" :aria-pressed="showZone" title="查看进入区域和出现时间的统计范围" @click="showZone = !showZone"><span class="zone-key"></span>{{ showZone ? '隐藏统计范围' : '显示统计范围' }}</button></div>
    <div v-if="activeClip" class="clip-playback" role="status"><div><strong>{{ clipFinished ? '片段回看已结束' : `${activeClip.title} · 片段回看` }}</strong><span>{{ timeLabel(activeClip.start) }}—{{ timeLabel(activeClip.end) }}{{ clipNotice ? ` · ${clipNotice}` : ' · 播放到片段结尾后自动暂停' }}</span></div><div><button v-if="clipFinished" class="text-button" @click="playClip(activeClip.start, activeClip.end, activeClip.title)">重播这段</button><button class="text-button" @click="cancelClip">退出片段回看</button></div></div>
    <div class="video-footnote"><Icon name="info" :size="15" /><p>编号方便对照物体；可能漏检，也可能把同一物体重复标记。</p></div>
  </section>
</template>

<style scoped>
.clip-playback{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 17px;background:#eef4ff;border-top:1px solid var(--line);color:var(--ink)}.clip-playback>div{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.clip-playback>div:first-child{display:block}.clip-playback strong{display:block;font-size:13px;font-weight:550}.clip-playback span{display:block;font-size:12px;line-height:1.8;color:#526985;margin-top:3px}.clip-playback button{min-height:44px;font-size:12px;white-space:nowrap}@media(max-width:639px){.clip-playback{align-items:start;flex-direction:column;padding:11px 12px}.clip-playback>div:last-child{width:100%;justify-content:space-between}}
</style>
