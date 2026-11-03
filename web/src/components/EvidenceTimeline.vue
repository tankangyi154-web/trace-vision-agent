<script setup lang="ts">
import { computed } from 'vue'
import { timeLabel } from '../api'
import type { ReviewFacts } from '../types'
const props = defineProps<{ facts: ReviewFacts; label: string; start: number; end: number; unknownTimes?: number[]; reviewed?: boolean }>()
const emit = defineEmits<{ seek: [t: number] }>()
const span = computed(() => Math.max(.1, props.end - props.start))
const position = (t: number) => `${Math.max(0, Math.min(100, (t - props.start) / span.value * 100))}%`
const width = (start: number, end: number) => `${Math.max(.4, Math.min(100, (end - start) / span.value * 100))}%`
</script>

<template>
  <div class="evidence-timeline">
    <div class="evidence-timeline-label"><strong>{{ label }}</strong><span>{{ reviewed ? '同一容忍规则重算' : '原始有效观测' }}</span></div>
    <div class="evidence-timeline-track">
      <div class="evidence-timeline-rail"></div>
      <button v-for="(interval, index) in facts.intervals" :key="`interval-${index}`" class="coverage-interval" :style="{ left: position(interval.start), width: width(interval.start, interval.end) }" @click="emit('seek', interval.start)" :aria-label="`${label}，区间${timeLabel(interval.start)}至${timeLabel(interval.end)}，点击定位`"><span>{{ (interval.end - interval.start).toFixed(1) }} 秒</span></button>
      <button v-for="(gap, index) in facts.gaps" :key="`gap-${index}`" class="coverage-gap" :style="{ left: position(gap.start), width: width(gap.start, gap.end) }" @click="emit('seek', gap.start)" :aria-label="`未知缺口 ${timeLabel(gap.start)}至${timeLabel(gap.end)}，点击定位`"><span>{{ gap.duration.toFixed(1) }} 秒未知</span></button>
      <button v-for="time in unknownTimes || []" :key="`unknown-${time}`" class="coverage-unresolved" :style="{ left: position(time - .05), width: width(time - .05, time + .05) }" @click="emit('seek', time)" :aria-label="`未决帧 ${timeLabel(time)}，点击定位`"><span>{{ timeLabel(time) }} 未决</span></button>
    </div>
    <div class="evidence-timeline-scale"><span>{{ timeLabel(start) }}</span><span>{{ timeLabel(end) }}</span></div>
  </div>
</template>
