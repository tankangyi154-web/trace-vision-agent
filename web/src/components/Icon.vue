<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  upload: 'M12 16V3m-5 5 5-5 5 5M4 14v6h16v-6',
  trace: 'M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5M8 15l4-7 4 4',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  play: 'M9 5l11 7-11 7V5Z',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
  chevron: 'm9 5 7 7-7 7',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  link: 'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
  target: 'M21 12a9 9 0 1 1-9-9M12 8a4 4 0 1 0 4 4M12 12l8-8M16 4h4v4',
  clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  check: 'm5 12 4 4L19 6',
  info: 'M12 11v6M12 7h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  refresh: 'M20 8a8 8 0 1 0 0 8M20 3v5h-5',
  close: 'm6 6 12 12M18 6 6 18',
  code: 'm8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18',
  grid: 'M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z',
  film: 'M3 3h18v18H3V3Zm4 0v18m10-18v18M3 8h4m-4 8h4m10-8h4m-4 8h4',
  chart: 'M4 3v17h17M8 16v-5m5 5V7m5 9V4',
}
</script>

<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.info" /></svg></template>
