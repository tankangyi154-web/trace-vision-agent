<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, errorText, timeLabel } from '../api'
import Icon from './Icon.vue'
import type { Scene } from '../types'

interface Evaluation {
  status: string; title?: string; protocol?: string
  dataset?: { scene_count: number; frames_annotated: number; objects_annotated: number; classes: string[]; sample_selection: string }
  metrics?: { name: string; value: number | null; unit?: string; description: string }[]
  per_scene?: { scene_id: string; frames: number; ground_truth: number; predictions: number; true_positives: number; false_positives: number; false_negatives: number; precision: number | null; recall: number | null }[]
  failures?: { id: string; scene_id: string; t: number; image_url: string; title: string; description: string }[]
  limitations?: string[]; configuration?: Record<string, unknown>; message?: string
}
defineProps<{ scenes: Scene[] }>()
const emit = defineEmits<{ view: [sceneId: string, t: number] }>()
const evaluation = ref<Evaluation | null>(null)
const error = ref('')
const loading = ref(false)
function percent(value: number | null): string { return value === null ? '未测量' : `${(value * 100).toFixed(1)}%` }
function metricValue(value: number | null, unit?: string): string { return value === null ? '未测量' : unit === 'ratio' ? value.toFixed(4) : value.toLocaleString('zh-CN', { maximumFractionDigits: 3 }) }
function metricUnit(unit?: string): string { return ({ ratio: '比率', frames: '帧', samples: '条' } as Record<string, string>)[unit || ''] || unit || '' }
async function load() { loading.value = true; error.value = ''; try { evaluation.value = await api<Evaluation>('/api/evaluation') } catch (e) { error.value = errorText(e) } finally { loading.value = false } }
onMounted(load)
</script>

<template>
  <div class="document-page evaluation-page">
    <header class="document-heading"><span class="document-kicker"><Icon name="chart" :size="20" /> 算法评测</span><h1>结果可复查，边界也公开。</h1><p>展示实际跑出的检测、跟踪与事件结果。小样本测量只说明这批片段的表现，不代表真实海事或生产环境的准确率。</p></header>
    <div v-if="loading" class="loading-state" role="status"><span class="spinner"></span>正在读取评测记录</div>
    <div v-else-if="error" class="page-error" role="alert"><p>{{ error }}</p><button class="button secondary" @click="load">重新读取</button></div>
    <template v-else-if="evaluation">
      <div v-if="evaluation.status !== 'measured'" class="notice"><Icon name="info" /><div><strong>评测尚未完成</strong><p>{{ evaluation.message || '本页不填未经实际跑测的准确率或性能提升。配置与测试范围可在下方查看。' }}</p></div></div>
      <div v-else-if="evaluation.protocol?.includes('尚未独立人工复核')" class="notice"><Icon name="info" /><div><strong>开发抽检，尚未独立人工复核</strong><p>下面的框匹配结果来自开发阶段小样本检查。它不是正式金标准，不代表全量检测、跟踪或真实部署的准确率。</p></div></div>
      <section v-if="evaluation.dataset" class="document-section"><h2>这次抽检了什么</h2><div class="evaluation-dataset"><div><strong>{{ evaluation.dataset.scene_count }}</strong><span>个公开视频片段</span></div><div><strong>{{ evaluation.dataset.frames_annotated }}</strong><span>个目视标注帧</span></div><div><strong>{{ evaluation.dataset.objects_annotated }}</strong><span>个目视参考框</span></div></div><p>{{ evaluation.dataset.sample_selection }}</p><p v-if="evaluation.dataset.classes?.length" class="muted">标注类别：{{ evaluation.dataset.classes.join('、') }}</p></section>
      <section v-if="evaluation.protocol" class="document-section protocol-section"><h2>测量方法</h2><p>{{ evaluation.protocol }}</p></section>
      <section v-if="evaluation.metrics?.length" class="document-section"><h2>开发抽检与处理记录</h2><div class="metric-grid"><article v-for="metric in evaluation.metrics" :key="metric.name"><h3>{{ metric.name }}</h3><strong>{{ metricValue(metric.value, metric.unit) }}<small v-if="metric.value !== null">{{ metricUnit(metric.unit) }}</small></strong><p>{{ metric.description }}</p></article></div></section>
      <section v-if="evaluation.per_scene?.length" class="document-section"><h2>逐片段核对</h2><div class="table-wrapper"><table><caption class="sr-only">各片段开发参考标注与检测匹配结果</caption><thead><tr><th scope="col">片段</th><th scope="col">标注帧</th><th scope="col">参考目标</th><th scope="col">TP / FP / FN</th><th scope="col">Precision</th><th scope="col">Recall</th></tr></thead><tbody><tr v-for="row in evaluation.per_scene" :key="row.scene_id"><th scope="row">{{ scenes.find(s => s.id === row.scene_id)?.title || row.scene_id }}</th><td>{{ row.frames }}</td><td>{{ row.ground_truth }}</td><td>{{ row.true_positives }} / {{ row.false_positives }} / {{ row.false_negatives }}</td><td>{{ percent(row.precision) }}</td><td>{{ percent(row.recall) }}</td></tr></tbody></table></div><p class="small muted">TP 为正确匹配，FP 为误检，FN 为漏检。这里只展示声明的开发参考标注抽检，尚未独立人工复核，不外推为全量 mAP 或身份跟踪指标。</p></section>
      <section v-if="evaluation.failures?.length" class="document-section"><h2>失败片段同样值得看</h2><div class="failure-grid"><article v-for="failure in evaluation.failures" :key="failure.id"><button class="failure-image" @click="emit('view', failure.scene_id, failure.t)"><img :src="failure.image_url" :alt="failure.title" loading="lazy" /><span><Icon name="play" :size="14" />{{ timeLabel(failure.t) }} · 回到片段</span></button><h3>{{ failure.title }}</h3><p>{{ failure.description }}</p></article></div></section>
      <section v-if="evaluation.limitations?.length" class="document-section"><h2>这些结论不能外推</h2><ul class="plain-list"><li v-for="limitation in evaluation.limitations" :key="limitation">{{ limitation }}</li></ul></section>
      <section class="document-section"><h2>检测与跟踪配置</h2><div v-if="scenes.length" class="configuration-list"><article v-for="scene in scenes" :key="scene.id"><h3>{{ scene.title }}</h3><dl><div><dt>检测模型</dt><dd>{{ scene.processing.model }}</dd></div><div><dt>跟踪器</dt><dd>{{ scene.processing.tracker }}</dd></div><div><dt>输入尺寸</dt><dd>{{ scene.processing.imgsz }}</dd></div><div><dt>置信度阈值</dt><dd>{{ scene.processing.confidence }}</dd></div><div><dt>NMS IoU</dt><dd>{{ scene.processing.iou }}</dd></div><div><dt>采样率</dt><dd>{{ scene.processing.sample_fps }} fps</dd></div></dl></article></div><details v-if="evaluation.configuration"><summary>完整评测配置</summary><pre>{{ JSON.stringify(evaluation.configuration, null, 2) }}</pre></details></section>
    </template>
  </div>
</template>
