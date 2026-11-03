<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import Icon from './Icon.vue'
import AnalysisDetails from './AnalysisDetails.vue'
import { timeLabel } from '../api'
import { statisticsScope } from '../statisticsFeedback'
import { buildPatrolItems, type PatrolItem } from '../patrol'
import { readPatrolReviews, savePatrolReview, reviewLabel, validScope, type ManualStatus, type PatrolReview, type ReviewStorage } from '../patrolReviews'
import { patrolDocument, patrolPayload, publicEvidenceUrl } from '../patrolReport'
import type { Analysis, Evidence, Scene } from '../types'

const props = defineProps<{ scene: Scene; analysis: Analysis; currentTime: number; selectedTrackId: string | null }>()
const emit = defineEmits<{ seek: [t: number, trackId?: string]; track: [id: string | null]; clip: [item: PatrolItem] }>()
const items = computed(() => buildPatrolItems(props.scene, props.analysis))
const selectedId = ref(items.value[0]?.id || '')
const selected = computed(() => items.value.find(item => item.id === selectedId.value) || items.value[0])
const limit = ref(6)
const scope = props.analysis.review_scope_id || ''
let storage: ReviewStorage = null
try { storage = localStorage } catch { /* Export remains available without browser storage. */ }
const loaded = readPatrolReviews(storage, scope)
const records = ref<Record<string, PatrolReview>>(loaded.records)
const storageAvailable = ref(loaded.available)
const checked = computed(() => items.value.filter(item => records.value[item.id]?.status === 'checked').length)
const uncertain = computed(() => items.value.filter(item => records.value[item.id]?.status === 'uncertain').length)
const pending = computed(() => items.value.length - checked.value - uncertain.value)
const gaps = computed(() => items.value.filter(item => item.kind === 'gap').length)
const notice = ref('')
const noticeError = ref(false)
const editorOpen = ref(false)
const picturesOpen = ref(false)
const drafts = ref<Record<string, { status: ManualStatus | ''; note: string }>>({})
const draft = computed(() => selected.value ? drafts.value[selected.value.id] : undefined)
const exporting = ref(false)
const imageDialog = ref<HTMLDialogElement | null>(null)
const activeEvidence = ref<Evidence | null>(null)
const reportQuery = computed(() => new URLSearchParams({ zone_id: props.analysis.zone_id, dwell_seconds: String(props.analysis.dwell_seconds) }).toString())

function select(item: PatrolItem) { selectedId.value = item.id; editorOpen.value = false; picturesOpen.value = false; notice.value = '' }
function edit() {
  const item = selected.value
  if (!item) return
  drafts.value[item.id] ||= { status: records.value[item.id]?.status || '', note: records.value[item.id]?.note || '' }
  editorOpen.value = !editorOpen.value
}
function save() {
  if (!selected.value || !draft.value?.status || !validScope(scope)) return
  const record: PatrolReview = { scope, item: selected.value.id, status: draft.value.status, note: draft.value.note.trim(), updatedAt: new Date().toISOString() }
  try {
    storageAvailable.value = savePatrolReview(storage, record)
    records.value = { ...records.value, [record.item]: record }
    noticeError.value = !storageAvailable.value
    notice.value = storageAvailable.value ? '核对结果已保存在当前浏览器，可导出证据单。' : '本次结果暂存在页面中，刷新前请导出证据单。'
    editorOpen.value = false
  } catch (error) { notice.value = error instanceof Error ? error.message : '未能保存核对记录。'; noticeError.value = true }
}
async function openImage(evidence: Evidence) { activeEvidence.value = evidence; await nextTick(); imageDialog.value?.showModal() }
function closeImage() { imageDialog.value?.close(); activeEvidence.value = null }
function download(content: string, type: string, extension: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url; link.download = `Trace-巡查核对单-${props.scene.id}-${props.analysis.zone_id}.${extension}`
  link.style.display = 'none'; document.body.appendChild(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
async function exportReport() {
  if (exporting.value) return
  exporting.value = true; notice.value = ''; noticeError.value = false
  const scene = props.scene, analysis = props.analysis, list = [...items.value]
  const saved = { ...records.value }, pictures: Record<string, string> = {}
  const evidence = [...new Map(list.flatMap(item => item.evidence).map(e => [e.id, e])).values()]
  let next = 0, missing = 0
  async function worker() {
    while (next < evidence.length) {
      const e = evidence[next++]!
      try {
        const url = publicEvidenceUrl(e.image_url, scene.id, location.origin)
        if (!url) throw new Error('Invalid evidence path')
        const response = await fetch(url)
        if (!response.ok) throw new Error('Evidence unavailable')
        const blob = await response.blob()
        if (!/^image\/(jpeg|png|webp)$/.test(blob.type)) throw new Error('Invalid evidence type')
        pictures[e.id] = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(blob) })
      } catch { missing++ }
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(4, evidence.length) }, worker))
    download(patrolDocument(scene, analysis, list, saved, pictures, location.origin), 'text/html;charset=utf-8', 'html')
    notice.value = missing ? `核对单已生成；${missing}张截图未能嵌入，单中保留了回看方式。请在浏览器中确认保存。` : '核对单已生成，包含当前设置、人工核对结果和实际截图。请在浏览器中确认保存。'
  } catch { notice.value = '导出未完成，请稍后重试；核对记录仍保留。'; noticeError.value = true }
  finally { exporting.value = false }
}
function exportJson() { download(JSON.stringify(patrolPayload(props.scene, props.analysis, items.value, records.value), null, 2), 'application/json;charset=utf-8', 'json') }
</script>

<template>
  <section class="patrol-panel" aria-labelledby="patrol-heading">
    <header class="patrol-heading"><div><p class="patrol-eyebrow">找到片段 → 核对画面 → 留下记录</p><h2 id="patrol-heading">巡查复核清单</h2><p>{{ statisticsScope(scene, analysis) }}</p></div><button class="button primary patrol-export" :disabled="exporting" @click="exportReport"><Icon :name="exporting ? 'refresh' : 'download'" :size="17" />{{ exporting ? '正在整理截图…' : '导出核对单' }}</button></header>
    <div class="patrol-summary" aria-label="核对进度"><span>片段记录 <strong>{{ items.length }}</strong></span><span>已核对 <strong>{{ checked }}</strong></span><span>待核对 <strong>{{ pending }}</strong></span><span v-if="uncertain">仍无法确认 <strong>{{ uncertain }}</strong></span></div>
    <p class="patrol-intro">{{ items.length ? `当前范围整理出${items.length}条可回看的片段记录${gaps ? `，其中${gaps}条包含需要进一步确认的识别中断` : ''}。${items.length === 1 ? '可直接回看这段，核对后留下说明。' : '选择一条，核对后留下说明。'}` : '当前设置下，没有达到指定时长、明确进出或存在相关识别中断的片段。可以调整统计设置，或展开下方完整记录。' }}</p>
    <p v-if="!storageAvailable" class="patrol-notice is-error" role="status">浏览器暂不能保存核对记录，刷新前请导出核对单。</p>
    <p v-if="notice" class="patrol-notice" :class="{ 'is-error': noticeError }" role="status">{{ notice }}</p>
    <div v-if="selected" class="patrol-workspace" :class="{ 'single-item': items.length === 1 }">
      <nav v-if="items.length > 1" class="patrol-list" aria-label="选择复核片段">
        <button v-for="item in items.slice(0, limit)" :key="item.id" class="patrol-choice" :aria-pressed="selected.id === item.id" @click="select(item)"><span class="patrol-choice-top"><span>{{ item.kind === 'gap' ? '连续性待确认' : item.kind === 'duration' ? '达到所设时长' : '进出记录' }}</span><span class="review-badge" :class="records[item.id]?.status">{{ reviewLabel(records[item.id]?.status) }}</span></span><strong>{{ item.title }}</strong><span class="patrol-choice-time">{{ timeLabel(item.start) }}—{{ timeLabel(item.end) }}</span></button>
        <button v-if="items.length > limit" class="text-button patrol-more" @click="limit += 10">再显示 {{ Math.min(10, items.length - limit) }} 条片段</button>
      </nav>
      <article class="patrol-record" :aria-label="selected.title">
        <div class="patrol-record-title"><h3>{{ selected.title }}</h3><span class="review-badge" :class="records[selected.id]?.status">{{ reviewLabel(records[selected.id]?.status) }}</span></div>
        <p class="patrol-description">{{ selected.description }}</p>
        <p class="patrol-range">回看片段 <strong>{{ timeLabel(selected.start) }}—{{ timeLabel(selected.end) }}</strong></p>
        <div class="patrol-actions"><button class="button primary" :disabled="selected.end <= selected.start" @click="emit('clip', selected)"><Icon name="play" :size="15" />回看这段</button><button class="button secondary" :disabled="!selected.evidence.length" @click="picturesOpen = !picturesOpen">{{ picturesOpen ? '收起关键画面' : '查看关键画面' }}</button><button class="button secondary" @click="edit">{{ editorOpen ? '收起核对表' : records[selected.id] ? '修改核对结果' : '记录核对结果' }}</button></div>
        <a v-if="selected.canInvestigate" class="patrol-investigate" href="#investigation">核对这艘船的5秒连续性 <Icon name="arrow" :size="16" /></a>
        <div v-if="picturesOpen" class="patrol-pictures"><figure v-for="evidence in selected.evidence" :key="evidence.id"><button @click="openImage(evidence)" :aria-label="`放大${selected.name}在${timeLabel(evidence.t)}的画面`"><img :src="evidence.image_url" :alt="`${selected.name}在${timeLabel(evidence.t)}的实际识别画面`" loading="lazy" :width="scene.width" :height="scene.height" /></button><figcaption><span>{{ timeLabel(evidence.t) }}</span><button class="text-button" @click="emit('seek', evidence.t, evidence.track_id)">回到视频 <Icon name="play" :size="12" /></button></figcaption></figure><p>截图时间与片段边界可能略有差异，点击时间回到视频核对。</p></div>
        <section v-if="editorOpen && draft" class="patrol-editor" aria-label="填写人工核对结果"><form @submit.prevent="save"><label :for="`review-status-${selected.id}`">这条记录的核对结果</label><select :id="`review-status-${selected.id}`" v-model="draft.status" required><option value="" disabled>请选择核对结果</option><option value="checked">已核对，与画面记录一致</option><option value="uncertain">仍无法确认，需要继续核对</option></select><label :for="`review-note-${selected.id}`">补充说明（选填）</label><textarea :id="`review-note-${selected.id}`" v-model="draft.note" maxlength="1200" rows="3" placeholder="写下看到的事实、无法确认的部分或后续需要核对的内容。"></textarea><p>人工意见与程序统计分别保留。点击保存后写入当前浏览器。</p><button class="button primary patrol-save" type="submit" :disabled="!draft.status || !validScope(scope)">保存核对结果</button></form></section>
        <div v-else-if="records[selected.id]" class="patrol-saved"><strong>人工核对：{{ reviewLabel(records[selected.id]!.status) }}</strong><p>{{ records[selected.id]!.note || '未填写补充说明。' }}</p><small>{{ new Date(records[selected.id]!.updatedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }} · 保存在当前浏览器</small></div>
        <details class="patrol-basis"><summary>查看判断依据</summary><ul><li v-for="fact in selected.facts" :key="fact">{{ fact }}</li><li v-for="gap in selected.gaps" :key="gap.id">识别中断：{{ timeLabel(gap.start) }}—{{ timeLabel(gap.end) }}，{{ gap.duration }}秒</li></ul><p>依据来自当前视频的实际识别记录；中断期间是否仍在场、是否属于同一真实物体，仍需结合画面核对。</p><code>数据与规则版本：{{ scope || '未提供' }}</code></details>
      </article>
    </div>
    <p class="patrol-footnote">这里整理可核对的事实，不自动判断违规或真实身份。核对记录按视频数据、范围和时长设置分别保存。</p>
    <details class="patrol-details"><summary>完整时间线、全片截图与原始统计</summary><AnalysisDetails :scene="scene" :analysis="analysis" :current-time="currentTime" :selected-track-id="selectedTrackId" @seek="(t, id) => emit('seek', t, id)" @track="id => emit('track', id)" /><div class="patrol-raw-reports"><span>原始程序统计</span><a v-for="format in ['markdown', 'html', 'json']" :key="format" :href="`/api/scenes/${scene.id}/report?${reportQuery}&format=${format}`" download>{{ format.toUpperCase() }}</a><button class="text-button" @click="exportJson">下载结构化核对记录 JSON</button></div></details>
    <dialog ref="imageDialog" class="evidence-dialog" @close="activeEvidence = null" @click="$event.target === imageDialog && closeImage()"><template v-if="activeEvidence"><div class="dialog-head"><strong>关键画面 · {{ timeLabel(activeEvidence.t) }}</strong><button class="icon-button" aria-label="关闭图片" @click="closeImage"><Icon name="close" /></button></div><img :src="activeEvidence.image_url" :alt="`实际识别画面，${timeLabel(activeEvidence.t)}`" /><div class="dialog-foot"><p>截图采样时间：{{ timeLabel(activeEvidence.t) }}</p><button class="button primary" @click="emit('seek', activeEvidence.t, activeEvidence.track_id); closeImage()">回到视频</button></div></template></dialog>
  </section>
</template>

<style scoped>
.patrol-panel{margin-top:32px;padding:28px;border:1px solid var(--line);border-radius:10px;background:white;color:var(--ink)}.patrol-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.patrol-heading h2{font-size:24px;line-height:1.5;margin:4px 0 7px}.patrol-heading p{font-size:13px;color:var(--muted);line-height:1.8}.patrol-heading .patrol-eyebrow{font-size:12px;color:#5c7190}.patrol-export{flex-shrink:0;min-height:44px;font-size:13px}.patrol-summary{display:flex;flex-wrap:wrap;gap:12px 28px;margin-top:22px;padding:15px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}.patrol-summary strong{font-size:18px;margin-left:7px;color:var(--ink)}.patrol-intro{font-size:14px;line-height:1.9;margin-top:17px;color:#536780}.patrol-workspace{display:grid;grid-template-columns:minmax(230px,.65fr) minmax(0,1.35fr);gap:26px;margin-top:22px}.patrol-workspace.single-item{grid-template-columns:1fr}.patrol-workspace.single-item .patrol-record{border:0;padding:0}.patrol-list{display:flex;flex-direction:column;gap:10px;align-self:start}.patrol-choice{display:block;width:100%;padding:15px;text-align:left;border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink)}.patrol-choice[aria-pressed=true]{border-color:#7494ef;background:#f3f6ff}.patrol-choice-top{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:11px;color:#657997}.patrol-choice strong{display:block;font-size:14px;line-height:1.8;font-weight:550;margin:10px 0 6px}.patrol-choice-time{font-size:12px;color:#60738d;font-variant-numeric:tabular-nums}.review-badge{display:inline-block;padding:3px 7px;background:#f1f4f8;color:#536780;border-radius:4px;font-size:11px;white-space:nowrap;flex-shrink:0}.review-badge.checked{background:#eaf6ef;color:#287052}.review-badge.uncertain{background:#fff2df;color:#835917}.patrol-record{min-width:0;padding-left:26px;border-left:1px solid var(--line)}.patrol-record-title{display:flex;align-items:start;justify-content:space-between;gap:12px}.patrol-record h3{font-size:19px;line-height:1.7;font-weight:600}.patrol-description{font-size:16px;line-height:1.95;margin-top:13px}.patrol-range{font-size:13px;color:var(--muted);margin-top:12px}.patrol-range strong{font-weight:400;color:var(--ink);margin-left:8px;font-variant-numeric:tabular-nums}.patrol-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}.patrol-actions button{font-size:13px;min-height:44px}.patrol-investigate{display:inline-flex;align-items:center;gap:8px;min-height:44px;margin-top:6px;font-size:13px}.patrol-pictures{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:17px}.patrol-pictures figure{margin:0;min-width:0}.patrol-pictures figure>button{display:block;width:100%;border-radius:6px;overflow:hidden;background:#eef2f7}.patrol-pictures img{width:100%;height:auto;aspect-ratio:16/9;object-fit:cover;display:block}.patrol-pictures figcaption{display:flex;align-items:center;flex-wrap:wrap;justify-content:space-between;gap:3px;font-size:11px;color:var(--muted)}.patrol-pictures .text-button{font-size:11px;min-height:34px;gap:4px}.patrol-pictures>p{grid-column:1/-1;font-size:12px;line-height:1.8;color:var(--muted)}.patrol-editor{margin-top:17px;padding:16px;background:#f6f8fc;border-radius:7px}.patrol-editor label{display:block;font-size:13px;margin:10px 0 7px}.patrol-editor label:first-child{margin-top:0}.patrol-editor select,.patrol-editor textarea{display:block;width:100%;min-height:44px;padding:10px;border:1px solid var(--line);border-radius:6px;background:white;color:var(--ink);font:inherit;font-size:14px}.patrol-editor textarea{resize:vertical;line-height:1.8}.patrol-editor p{font-size:12px;color:var(--muted);line-height:1.8;margin:9px 0 12px}.patrol-save{min-height:44px;font-size:13px}.patrol-saved{background:#f4f8f5;padding:13px 15px;border-radius:6px;margin-top:18px}.patrol-saved strong{font-size:13px;font-weight:550}.patrol-saved p{font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;margin-top:5px}.patrol-saved small{display:block;font-size:11px;color:var(--muted);margin-top:8px}.patrol-basis{margin-top:19px;border-top:1px solid var(--line);padding-top:8px}.patrol-basis summary,.patrol-details>summary{font-size:13px;color:#526985;cursor:pointer;min-height:44px;padding:10px 0;line-height:1.8}.patrol-basis ul{padding-left:20px;font-size:13px;line-height:1.9;margin:5px 0 8px}.patrol-basis p{font-size:12px;line-height:1.8;color:var(--muted)}.patrol-basis code{font-size:11px;overflow-wrap:anywhere;display:block;margin-top:9px;color:var(--muted)}.patrol-footnote{font-size:12px;line-height:1.9;color:var(--muted);margin-top:22px}.patrol-details{margin-top:12px;border-top:1px solid var(--line)}.patrol-details :deep(.analysis-panel){border:0;padding:0;margin-top:15px;border-radius:0}.patrol-raw-reports{display:flex;align-items:center;gap:18px;flex-wrap:wrap;font-size:12px;margin-top:20px;border-top:1px solid var(--line);padding-top:12px}.patrol-raw-reports a,.patrol-raw-reports button{min-height:44px;display:inline-flex;align-items:center;font-size:12px}.patrol-notice{font-size:13px;line-height:1.8;padding:10px 12px;margin-top:14px;background:#eaf6ef;color:#28634d;border-radius:6px}.patrol-notice.is-error{color:#963c2e;background:#fff1ed}.patrol-more{min-height:44px;font-size:13px;justify-content:center}button:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #91aafd;outline-offset:3px}@media(max-width:900px){.patrol-workspace{grid-template-columns:1fr;gap:22px}.patrol-record{border-left:0;border-top:1px solid var(--line);padding:20px 0 0}.patrol-choice strong{margin-top:6px}.patrol-choice{padding:12px 14px}}@media(max-width:639px){.patrol-panel{padding:20px 15px;margin-top:24px}.patrol-heading{align-items:start;flex-direction:column;gap:13px}.patrol-heading h2{font-size:21px}.patrol-export{width:100%}.patrol-summary{gap:12px 20px;margin-top:17px}.patrol-record h3{font-size:17px}.patrol-description{font-size:15px}.patrol-pictures{grid-template-columns:1fr}.patrol-pictures .text-button{min-height:44px;font-size:12px}.patrol-pictures figcaption{font-size:12px}.patrol-actions{gap:9px}.patrol-actions button{flex:1 1 135px}.patrol-editor select,.patrol-editor textarea{font-size:16px}.patrol-record-title{gap:8px}.patrol-heading .patrol-eyebrow{font-size:11px}.patrol-raw-reports{gap:6px 16px}.patrol-footnote{font-size:12px}}
</style>
