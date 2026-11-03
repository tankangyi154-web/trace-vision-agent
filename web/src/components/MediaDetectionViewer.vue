<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref, watch } from 'vue'
import { boxesAtTime, classColor, layoutLabels, type MediaTarget } from '../mediaAnnotations'
import trackingPolicy from '../../../vision/upload-tracking.json'

type Result = { kind: 'image' | 'video'; media_url: string; annotation_source_url?: string; poster_url: string; duration: number; width: number; height: number; sample_fps?: number; targets: MediaTarget[]; counts: { label: string; name: string }[]; quality?: { low_resolution: boolean; note: string }; processing?: { tracking_policy?: string } }
const props = defineProps<{ result: Result; selectedTarget: string | null; initialTime?: number }>()
const emit = defineEmits<{ time: [number]; error: []; select: [string] }>()
const video = ref<HTMLVideoElement | null>(null), stage = ref<HTMLElement | null>(null), fullscreenRoot = ref<HTMLElement | null>(null)
const time = ref(props.initialTime || 0), size = ref({ width: 600, height: 480 }), category = ref(''), sourceOnly = ref(false), focus = ref(!!props.selectedTarget), showNames = ref(true)
const fullscreen = ref(false), expandError = ref('')
const dynamic = computed(() => !!props.result.annotation_source_url)
const source = computed(() => props.result.annotation_source_url || props.result.media_url)
const visible = computed(() => boxesAtTime(props.result.targets, time.value, props.result.sample_fps || 5, props.result.kind === 'image')
  .filter(b => (!category.value || b.label === category.value) && (!focus.value || !props.selectedTarget || b.id === props.selectedTarget)))
const labels = computed(() => layoutLabels(visible.value, size.value.width, size.value.height))
let observer: ResizeObserver | undefined, callback: number | undefined, disposed = false, pendingSeek = props.initialTime || 0
function updateTime(t: number) { time.value = t; emit('time', t) }
function frameLoop() {
  if (disposed || !video.value || !('requestVideoFrameCallback' in video.value)) return
  callback = video.value.requestVideoFrameCallback((_, metadata) => { updateTime(metadata.mediaTime); frameLoop() })
}
function seek(t: number) { pendingSeek = t; if (video.value) { video.value.currentTime = t; video.value.pause() }; updateTime(t) }
function pause() { video.value?.pause() }
function loaded() { seek(Math.min(pendingSeek, props.result.duration)); frameLoop() }
async function expand() {
  expandError.value = ''
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await fullscreenRoot.value?.requestFullscreen() }
  catch { expandError.value = '浏览器暂不支持全屏，可使用浏览器缩放查看。' }
}
function fullscreenChange() { fullscreen.value = document.fullscreenElement === fullscreenRoot.value }
watch(() => props.selectedTarget, value => { focus.value = !!value; category.value = ''; sourceOnly.value = false })
watch(source, (_, old) => { if (old) pendingSeek = time.value })
watch(() => props.result.targets, () => { if (category.value && !props.result.counts.some(c => c.label === category.value)) category.value = '' })
onMounted(async () => {
  await nextTick()
  observer = new ResizeObserver(entries => { const r = entries[0]!.contentRect; size.value = { width: r.width, height: r.height } })
  if (stage.value) observer.observe(stage.value)
  document.addEventListener('fullscreenchange', fullscreenChange)
})
onScopeDispose(() => { disposed = true; observer?.disconnect(); if (callback !== undefined) video.value?.cancelVideoFrameCallback(callback); document.removeEventListener('fullscreenchange', fullscreenChange) })
defineExpose({ seek, pause, get currentTime() { return video.value?.currentTime ?? time.value } })
</script>

<template>
  <div ref="fullscreenRoot" class="detection-viewer" :style="{ '--media-aspect': result.width / result.height }">
    <div class="detection-tools">
      <div v-if="dynamic" class="detection-categories" role="group" aria-label="按类型查看识别框">
        <button :aria-pressed="!category" @click="category = ''; focus = false">全部类型</button>
        <button v-for="row in result.counts" :key="row.label" :aria-pressed="category === row.label" @click="category = category === row.label ? '' : row.label; focus = false; sourceOnly = false"><i :style="{ background: classColor(row.label) }"></i>{{ row.name }}</button>
      </div>
      <button v-if="dynamic" :aria-pressed="sourceOnly" @click="sourceOnly = !sourceOnly">{{ sourceOnly ? '显示识别框' : '查看原片' }}</button>
      <button @click="expand">{{ fullscreen ? '退出全屏' : '放大画面' }}</button>
    </div>
    <div ref="stage" class="detection-stage" :style="{ aspectRatio: `${result.width}/${result.height}` }">
      <video v-if="result.kind === 'video'" ref="video" :src="source" :poster="dynamic ? undefined : result.poster_url" controls playsinline preload="auto" aria-label="本次上传视频的识别结果" @loadedmetadata="loaded" @timeupdate="video && updateTime(video.currentTime)" @seeked="video && updateTime(video.currentTime)" @error="emit('error')"></video>
      <img v-else :src="source" :width="result.width" :height="result.height" alt="本次上传图片的识别结果" @error="emit('error')" />
      <svg v-if="dynamic && !sourceOnly" class="detection-overlay" :viewBox="`0 0 ${size.width} ${size.height}`" aria-label="按物体类型着色的识别框">
        <g v-for="box in labels" :key="box.id" :data-label="box.label" :data-id="box.id">
          <rect class="box-halo" :x="box.rect[0]" :y="box.rect[1]" :width="box.rect[2]-box.rect[0]" :height="box.rect[3]-box.rect[1]" />
          <rect class="object-box" :class="{ selected: box.id === selectedTarget }" :x="box.rect[0]" :y="box.rect[1]" :width="box.rect[2]-box.rect[0]" :height="box.rect[3]-box.rect[1]" :stroke="box.color" />
          <template v-if="showNames">
            <line :x1="box.anchor[0]" :y1="box.anchor[1]" :x2="box.end[0]" :y2="box.end[1]" :stroke="box.color" stroke-width="1" />
            <rect :x="box.labelRect[0]" :y="box.labelRect[1]" :width="box.labelRect[2]-box.labelRect[0]" height="24" rx="3" :fill="box.color" />
            <text :x="box.labelRect[0]+6" :y="box.labelRect[1]+17" fill="white" font-size="14">{{ box.text }}</text>
          </template>
        </g>
      </svg>
    </div>
    <div v-if="dynamic" class="detection-options">
      <label><input v-model="showNames" type="checkbox" :disabled="sourceOnly" />显示类型与编号</label>
      <label v-if="selectedTarget"><input v-model="focus" type="checkbox" :disabled="sourceOnly" />只看选中的物体</label>
      <span>{{ sourceOnly ? '原片预览' : `当前画面 ${visible.length} 个框` }}</span>
    </div>
    <p v-if="result.quality?.low_resolution" class="detection-note">{{ result.quality.note }}</p>
    <p v-if="result.kind === 'video' && result.processing?.tracking_policy !== trackingPolicy.version" class="detection-note" role="status">这份结果来自旧版跟踪，请重新上传视频使用改进后的编号关联。</p>
    <p v-if="!dynamic" class="detection-note">这是一份旧版结果，重新上传分析后可按类型筛选和切换原片。</p>
    <p v-if="expandError" class="detection-note" role="status">{{ expandError }}</p>
  </div>
</template>

<style scoped>
.detection-viewer{width:100%;min-width:0;color:#334155}.detection-tools{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:10px 12px;background:#fff;border-bottom:1px solid #dde3eb}.detection-tools button{min-height:40px;border:1px solid #dce2ea;background:#fff;color:#475569;border-radius:6px;padding:8px 10px;font:inherit;font-size:12px;cursor:pointer}.detection-categories{display:flex;flex-wrap:wrap;gap:6px;margin-right:auto}.detection-categories button{display:flex;align-items:center;gap:6px}.detection-categories i{width:9px;height:9px;border-radius:2px}.detection-tools button[aria-pressed=true]{border-color:#8ba2e4;background:#f0f4ff;color:#2348b2}.detection-stage{position:relative;max-height:650px;max-width:100%;width:auto;margin:auto;overflow:hidden;background:#111827}.detection-stage video,.detection-stage img{display:block;width:100%;height:100%;object-fit:contain}.detection-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.box-halo{fill:none;stroke:#fff;stroke-opacity:.8;stroke-width:3}.object-box{fill:none;stroke-width:1.8}.object-box.selected{stroke-width:3}.detection-options{display:flex;flex-wrap:wrap;gap:8px 16px;padding:4px 14px;background:#fff;font-size:12px;color:#475569}.detection-options label{display:flex;align-items:center;min-height:40px;gap:5px;cursor:pointer}.detection-options input{accent-color:#3159df;width:16px;height:16px}.detection-options>span{margin-left:auto;align-self:center;color:#64748b}.detection-note{padding:0 14px 12px;margin:0;background:white;font-size:12px;line-height:1.8;color:#64748b}.detection-tools button:focus-visible,.detection-options input:focus-visible{outline:3px solid #91aafd;outline-offset:2px}.detection-viewer:fullscreen{background:#111827;display:flex;flex-direction:column;justify-content:center;padding:0 16px}.detection-viewer:fullscreen .detection-stage{flex:0 1 auto;max-height:calc(100dvh - 170px);max-width:calc((100dvh - 170px)*var(--media-aspect,1.25));width:100%}.detection-viewer:fullscreen .detection-tools,.detection-viewer:fullscreen .detection-options,.detection-viewer:fullscreen .detection-note{flex-shrink:0}.detection-viewer:fullscreen .detection-note{padding-top:8px}@media(max-width:600px){.detection-tools{padding:7px;gap:5px}.detection-tools button{min-height:44px;padding:7px 9px}.detection-options{padding:3px 8px}.detection-note{padding:0 9px 10px}.detection-viewer:fullscreen{padding:0 4px}}
</style>
<style scoped>
.detection-stage{width:100%;max-width:min(100%,calc(650px * var(--media-aspect,1.25)))}
</style>
