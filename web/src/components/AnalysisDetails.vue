<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from './Icon.vue'
import { eventNames, timeLabel } from '../api'
import { targetName, eventDescription } from '../plainLanguage'
import { statisticsScope } from '../statisticsFeedback'
import type { Analysis, Evidence, Scene, VideoEvent } from '../types'

const props = defineProps<{ scene: Scene; analysis: Analysis; currentTime: number; selectedTrackId: string | null }>()
const emit = defineEmits<{ seek: [t: number, trackId?: string]; track: [id: string | null] }>()
function label(id: string) { return targetName(id, props.scene.tracks.find(track => track.id === id)?.label) }
const eventFilter = ref('all')
const eventLimit = ref(15)
const evidenceLimit = ref(6)
const activeEvidence = ref<Evidence | null>(null)
const dialog = ref<HTMLDialogElement | null>(null)
const events = computed(() => props.analysis.events.filter((event) => (eventFilter.value === 'all' || event.type === eventFilter.value) && (!props.selectedTrackId || event.track_id === props.selectedTrackId)))
const evidence = computed(() => props.analysis.evidence.filter((item) => !props.selectedTrackId || item.track_id === props.selectedTrackId))
const ranked = computed(() => [...props.analysis.dwell].sort((a, b) => b.observed_seconds - a.observed_seconds))
function openEvidence(item: Evidence) { activeEvidence.value = item; dialog.value?.showModal() }
function closeEvidence() { dialog.value?.close(); activeEvidence.value = null }
function jumpEvent(event: VideoEvent) { emit('seek', event.start, event.track_id) }
function percent(t: number): string { return `${Math.max(0, Math.min(100, t / props.scene.duration * 100))}%` }
</script>

<template>
  <section class="analysis-panel" aria-labelledby="analysis-heading">
    <div class="section-heading"><div><h2 id="analysis-heading">详细统计与全部画面</h2><p>{{ statisticsScope(scene, analysis) }}。当前范围含{{ analysis.summary.tracks }}个相关标记，全片共{{ analysis.summary.clip_tracks ?? scene.tracks.length }}个标记；标记数不等于真实唯一物体数。</p></div><span class="computed-tag"><Icon name="check" :size="14" /> 根据画面整理</span></div>
    <div class="analysis-stats">
      <div><span>区域相关标记</span><strong>{{ analysis.summary.tracks }}<small>个</small></strong></div>
      <div><span>进入所选区域</span><strong>{{ analysis.summary.entries }}<small>次</small></strong></div>
      <div><span>连续出现至少{{ analysis.dwell_seconds }}秒</span><strong class="event-number">{{ analysis.summary.dwell_alerts }}<small>段</small></strong></div>
      <div><span>暂时没识别到</span><strong>{{ analysis.summary.observation_gaps }}<small>次</small></strong></div>
    </div>

    <div class="timeline-block">
      <div class="timeline-legend"><span><i class="legend-enter"></i>进入区域</span><span><i class="legend-dwell"></i>出现较久</span><span><i class="legend-gap"></i>暂时没识别到</span></div>
      <div class="timeline-plot" aria-hidden="true">
        <div class="timeline-line"></div>
        <span v-for="event in events" :key="event.id" class="timeline-event" :class="`event-${event.type}`" :style="{ left: percent(event.start), width: event.duration > 0 ? `${Math.max(0.8, Math.min(event.duration, scene.duration - event.start) / scene.duration * 100)}%` : '5px' }"></span>
        <span class="playhead" :style="{ left: percent(currentTime) }"></span>
      </div>
      <div class="timeline-ticks"><span>{{ timeLabel(0) }}</span><span>{{ timeLabel(scene.duration / 2) }}</span><span>{{ timeLabel(scene.duration) }}</span></div>
    </div>

    <div class="analysis-columns">
      <section class="events-section" aria-labelledby="events-heading">
        <div class="list-heading"><h3 id="events-heading">画面记录 <span>{{ events.length }}</span></h3><label class="sr-only" for="event-type">筛选画面记录</label><select id="event-type" v-model="eventFilter"><option value="all">全部记录</option><option value="enter">进入区域</option><option value="dwell">出现较久</option><option value="observation_gap">暂时没识别到</option><option value="initial_presence">已在区域内</option><option value="exit">离开区域</option></select></div>
        <div v-if="!events.length" class="empty-state"><Icon name="target" :size="25" /><p>当前没有符合条件的记录。</p><button v-if="selectedTrackId || eventFilter !== 'all'" class="text-button" @click="emit('track', null); eventFilter = 'all'">清除筛选</button><p v-else class="muted small">可以换个区域或调整提示时间。</p></div>
        <ol v-else class="event-list">
          <li v-for="event in events.slice(0, eventLimit)" :key="event.id">
            <button class="event-row" @click="jumpEvent(event)">
              <span class="event-line-icon" :class="`event-${event.type}`"><Icon :name="event.type === 'dwell' ? 'clock' : event.type === 'observation_gap' ? 'info' : 'target'" :size="16" /></span>
              <span class="event-description"><span class="event-title">{{ eventNames[event.type] }}<span class="track-number">{{ targetName(event.track_id, event.label) }}</span></span><span class="event-subtitle">{{ eventDescription(event, analysis.dwell_seconds) }}</span></span>
              <span class="event-time">{{ timeLabel(event.start) }}<small v-if="event.duration > 0">{{ event.duration.toFixed(1) }} 秒<span v-if="event.censored" class="interval-note">未看到完整过程</span></small></span>
              <Icon name="chevron" :size="16" />
            </button>
          </li>
        </ol>
        <button v-if="events.length > eventLimit" class="text-button show-more" @click="eventLimit += 30">再显示 {{ Math.min(30, events.length - eventLimit) }} 条记录</button>
      </section>
      <section class="tracks-section" aria-labelledby="tracks-heading">
        <div class="list-heading"><h3 id="tracks-heading">在区域里出现多久</h3><button v-if="selectedTrackId" class="text-button" @click="emit('track', null)">查看全部</button></div>
        <p class="small muted">按能确认的画面累计，中间没看见的时间不计入。</p>
        <div v-if="!ranked.length" class="empty-state"><p>还没有识别到物体出现在这个区域。</p></div>
        <ol v-else class="track-ranking">
          <li v-for="(item, index) in ranked.slice(0, 8)" :key="item.track_id">
            <button :aria-pressed="selectedTrackId === item.track_id" @click="emit('track', selectedTrackId === item.track_id ? null : item.track_id)"><span class="rank-index">{{ index + 1 }}</span><span class="rank-track">{{ targetName(item.track_id, item.label) }}</span><span class="rank-meter" aria-hidden="true"><i :style="{ width: `${ranked[0]!.observed_seconds > 0 ? item.observed_seconds / ranked[0]!.observed_seconds * 100 : 0}%` }"></i></span><strong>{{ item.observed_seconds.toFixed(1) }}<small> 秒</small></strong></button>
          </li>
        </ol>
        <p v-if="selectedTrackId" class="track-selected-note">已选中{{ label(selectedTrackId) }}，视频和下方截图会对应显示它。</p>
        <p class="boundary-note">视频外的出现和离开时间无法确认。</p>
      </section>
    </div>

    <section class="evidence-section" aria-labelledby="evidence-heading">
      <div class="section-heading"><div><h3 id="evidence-heading">全片识别截图 <span class="count">{{ evidence.length }}</span></h3><p>此处保留完整画面，可能包含所选范围以外的时间。点击图片放大，点击时间回到视频。</p></div><button v-if="selectedTrackId" class="text-button" @click="emit('track', null)">清除目标筛选</button></div>
      <div v-if="!evidence.length" class="empty-state"><p>这个物体还没有可回看的截图。</p></div>
      <div v-else class="evidence-grid">
        <article v-for="item in evidence.slice(0, evidenceLimit)" :key="item.id" class="evidence-card">
          <button class="evidence-image" @click="openEvidence(item)" :aria-label="`放大${label(item.track_id)}在${timeLabel(item.t)}的画面`"><img :src="item.image_url" :alt="`${label(item.track_id)}在${timeLabel(item.t)}的识别画面`" loading="lazy" :width="scene.width" :height="scene.height" /><span>{{ timeLabel(item.t) }}</span><span class="image-open">放大查看</span></button>
          <div class="evidence-caption"><strong>{{ label(item.track_id) }}</strong><button class="timestamp" @click="emit('seek', item.t, item.track_id)"><Icon name="play" :size="12" />{{ timeLabel(item.t) }}</button></div>

        </article>
      </div>
      <button v-if="evidence.length > evidenceLimit" class="button secondary show-more" @click="evidenceLimit += 12">查看更多画面（还有 {{ evidence.length - evidenceLimit }} 张）</button>
    </section>
    <dialog ref="dialog" class="evidence-dialog" @click="($event.target === dialog) && closeEvidence()" @close="activeEvidence = null">
      <template v-if="activeEvidence"><div class="dialog-head"><strong>{{ label(activeEvidence.track_id) }} · {{ timeLabel(activeEvidence.t) }}</strong><button class="icon-button" @click="closeEvidence" aria-label="关闭图片"><Icon name="close" /></button></div><img :src="activeEvidence.image_url" :alt="`${label(activeEvidence.track_id)}，${timeLabel(activeEvidence.t)}的画面`" /><div class="dialog-foot"><p>可回到视频核对这张截图。</p><button class="button primary" @click="emit('seek', activeEvidence.t, activeEvidence.track_id); closeEvidence()"><Icon name="play" :size="15" />回看 {{ timeLabel(activeEvidence.t) }}</button></div></template>
    </dialog>
  </section>
</template>
