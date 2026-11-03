<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'
import { shortZone } from '../plainLanguage'
import { statisticsScope, validStatisticsSeconds } from '../statisticsFeedback'
import type { Analysis, Scene } from '../types'

const props = defineProps<{ scene: Scene; analysis: Analysis | null; loading: boolean; feedback: string; error: string }>()
const zone = defineModel<string>('zone', { required: true })
const seconds = defineModel<number | string>('seconds', { required: true })
const emit = defineEmits<{ apply: []; showRegion: [] }>()
const changed = computed(() => !!props.analysis && (zone.value !== props.analysis.zone_id || Number(seconds.value) !== props.analysis.dwell_seconds))
const valid = computed(() => validStatisticsSeconds(seconds.value))
const applied = computed(() => props.analysis ? statisticsScope(props.scene, props.analysis) : props.loading ? '正在准备统计结果…' : '尚未生成统计结果')
</script>

<template>
  <section class="statistics-settings" aria-label="区域统计设置">
    <details>
      <summary>
        <span class="settings-heading">统计设置 <span v-if="changed" class="settings-pending">待应用</span></span>
        <span class="settings-current">{{ applied }}</span><Icon name="chevron" :size="16" class="settings-chevron" />
      </summary>
      <div class="settings-content">
        <p class="settings-help">选择统计范围，并设置出现时长的判断条件。进出记录与相关识别中断也会整理到清单中。</p>
        <form class="settings-form" @submit.prevent="emit('apply')">
          <div class="settings-field"><label for="region">统计范围</label><select id="region" v-model="zone" :disabled="loading"><option v-for="item in scene.zones" :key="item.id" :value="item.id">{{ shortZone(item.name || `区域 ${item.id}`) }}</option></select></div>
          <div class="settings-field"><label for="threshold">连续出现至少</label><div class="settings-seconds"><input id="threshold" v-model.number="seconds" :disabled="loading" type="number" min="0.5" max="60" step="0.5" required aria-describedby="statistics-help" /><span>秒</span></div></div>
          <button class="button secondary statistics-submit" type="submit" :disabled="loading || !valid || (!changed && !!analysis && !error)"><span v-if="loading" class="spinner"></span><Icon v-else name="refresh" :size="16" />{{ loading ? '正在统计' : '重新统计' }}</button>
        </form>
        <p v-if="!valid" class="settings-error" role="alert">请输入0.5到60秒之间的时长。</p>
        <p id="statistics-help" class="settings-note">{{ changed ? '设置尚未应用，点击“重新统计”后更新下方结果。' : analysis ? '下方结果正在使用以上设置。' : '点击“重新统计”，生成这段视频的结果。' }}</p>
        <button v-if="analysis" class="settings-region" type="button" @click="emit('showRegion')">在视频中查看当前统计范围 <Icon name="target" :size="14" /></button>
      </div>
    </details>
    <p v-if="loading" class="statistics-status" role="status">正在统计所选范围的出现记录…</p>
    <p v-else-if="error" class="statistics-status is-error" role="alert"><span>重新统计未完成。{{ error }} {{ analysis ? `当前结果仍使用“${applied}”。` : '' }}<button class="statistics-retry" type="button" :disabled="!valid || loading" @click="emit('apply')">重试统计</button></span></p>
    <p v-else-if="changed" class="statistics-status is-pending" role="status">设置尚未应用，当前结果仍使用“{{ applied }}”。</p>
    <p v-else-if="feedback" class="statistics-status is-success" role="status"><Icon name="check" :size="16" /><span>{{ feedback }}</span></p>
  </section>
</template>

<style scoped>
.statistics-settings{margin-top:16px;color:var(--ink)}details{border:1px solid var(--line);border-radius:8px;background:white}summary{display:flex;align-items:center;gap:12px;min-height:58px;padding:12px 16px;cursor:pointer;list-style:none}summary::-webkit-details-marker{display:none}.settings-heading{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:550;flex-shrink:0}.settings-current{margin-left:auto;color:var(--muted);font-size:12px;line-height:1.7}.settings-chevron{flex-shrink:0;transition:transform .15s}details[open] .settings-chevron{transform:rotate(90deg)}.settings-pending{font-size:11px;color:#93601c;background:#fff4df;border-radius:4px;padding:2px 6px;font-weight:400}.settings-content{border-top:1px solid var(--line);padding:16px}.settings-help{font-size:13px;line-height:1.8;color:var(--muted);margin:0 0 16px}.settings-form{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end}.settings-field label{display:block;font-size:13px;margin-bottom:7px}.settings-field select{height:46px;max-width:240px;min-width:145px;padding:0 32px 0 12px;border:1px solid var(--line);border-radius:6px;background:white;color:var(--ink);font:inherit;font-size:14px}.settings-seconds{display:flex;align-items:center;height:46px;border:1px solid var(--line);border-radius:6px;overflow:hidden}.settings-seconds input{width:76px;min-width:0;height:100%;padding:9px 0 9px 12px;border:0;background:transparent;color:var(--ink);font:inherit;font-size:15px}.settings-seconds span{padding:0 12px 0 7px;color:var(--muted);font-size:13px}.statistics-submit{min-height:46px;font-size:13px}.settings-note,.settings-error{font-size:12px;line-height:1.8;margin:12px 0 0}.settings-note{color:var(--muted)}.settings-error{color:#a63c30}.settings-region{display:inline-flex;align-items:center;gap:6px;min-height:44px;font-size:12px;color:var(--blue);margin-top:4px}.statistics-status{display:flex;align-items:flex-start;gap:7px;font-size:13px;line-height:1.9;margin:10px 0 0;padding:10px 12px;border-radius:6px;background:#f5f7fb;color:#536780}.statistics-status>svg{flex-shrink:0;margin-top:4px}.statistics-retry{display:inline-flex;align-items:center;min-height:44px;margin-left:10px;font-size:13px;text-decoration:underline;text-underline-offset:3px}.is-success{color:#246653;background:#edf7f2}.is-pending{color:#855b24;background:#fff8ec}.is-error{color:#a63c30;background:#fff2ef}summary:focus-visible,button:focus-visible,select:focus-visible{outline:3px solid #91aafd;outline-offset:3px}.settings-seconds:focus-within{outline:3px solid #91aafd;outline-offset:3px}.settings-seconds input:focus-visible{outline:0}@media(max-width:639px){summary{gap:8px;padding:12px;flex-wrap:wrap}.settings-current{order:3;width:100%;margin-left:0}.settings-chevron{margin-left:auto}.settings-content{padding:14px 12px}.settings-form{gap:14px 12px}.settings-field:first-child{flex:1}.settings-field select{width:100%;min-width:0;max-width:none}.settings-seconds input{font-size:16px;width:65px}.statistics-submit{width:100%}.statistics-status{font-size:13px}.settings-region{font-size:13px}}@media(prefers-reduced-motion:reduce){.settings-chevron{transition:none}}
</style>
