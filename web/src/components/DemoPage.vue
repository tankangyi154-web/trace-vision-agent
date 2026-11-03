<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue'
import Icon from './Icon.vue'
import MediaDetectionViewer from './MediaDetectionViewer.vue'
import { api, errorText, timeLabel } from '../api'
import { offlineExamples } from '../buildMode'
import { demoHref } from '../navigation'
import { classColor } from '../mediaAnnotations'
import { writeMediaCache, rememberMediaRecord } from '../mediaPersistence'
import type { GalleryItem, PreparedDemo, DemoProof } from '../preparedDemos'
import type { Health } from '../types'
import '../media.css'

const props=defineProps<{ demoId: string; demos: GalleryItem[]; health: Health | null }>()
const demo=ref<PreparedDemo | null>(null), loading=ref(false), error=ref(''), opening=ref(false)
const selected=ref<string | null>(null), time=ref(0), guideIndex=ref(0), playbackError=ref(false)
const player=ref<InstanceType<typeof MediaDetectionViewer> | null>(null)
const mediaPanel=ref<HTMLElement | null>(null), panel=ref<'media'|'chat'>('media')
const guide=computed(()=>demo.value?.guides[guideIndex.value])
const selectedObject=computed(()=>demo.value?.result.targets.find(t=>t.id===selected.value))
let generation=0,alive=true
async function load() {
  const current=++generation;loading.value=true;error.value='';demo.value=null;player.value?.pause()
  try {
    const data=await api<PreparedDemo>(`/api/presets/${encodeURIComponent(props.demoId)}`)
    if(!alive || current!==generation)return
    selected.value=null;time.value=0;guideIndex.value=0;panel.value='media';playbackError.value=false
    try {
      const saved=JSON.parse(localStorage.getItem('trace-demo-view-'+data.id)||'null')
      if(saved?.version===data.version){
        if(data.result.targets.some(t=>t.id===saved.target))selected.value=saved.target
        if(typeof saved.time==='number' && Number.isFinite(saved.time))time.value=Math.max(0,Math.min(data.duration,saved.time))
      }
    }catch{/* A saved example view is optional. */}
    demo.value=data
  }catch(e){if(alive && current===generation)error.value=errorText(e)}
  finally{if(alive && current===generation)loading.value=false}
}
function save() {
  if(!demo.value)return
  try{localStorage.setItem('trace-demo-view-'+demo.value.id,JSON.stringify({version:demo.value.version,target:selected.value,time:time.value}))}catch{/* Examples still work without storage. */}
}
function seek(t:number,target?:string) {
  if(target)selected.value=target
  time.value=t;panel.value='media';player.value?.seek(t)
  void nextTick(()=>mediaPanel.value?.scrollIntoView({block:'nearest'}))
}
function chooseTarget(id:string) {
  const target=demo.value?.result.targets.find(t=>t.id===id)
  if(target)seek(target.first_seen,id)
}
function chooseGuide(index:number) {
  guideIndex.value=index
  const item=demo.value?.guides[index]
  if(item?.target_id){selected.value=item.target_id;seek(item.citations[0]?.t||0,item.target_id)}
  panel.value='chat'
}
function proof(item:DemoProof){seek(item.t,guide.value?.target_id)}
async function continueAsking() {
  if(!demo.value || opening.value)return
  opening.value=true;error.value=''
  try {
    const session=await api<{session_id:string}>('/api/sessions',{method:'POST'})
    const job=await api<{id:string}>(`/api/presets/${demo.value.id}/open`,{method:'POST',headers:{'X-Session-ID':session.session_id}})
    try{localStorage.setItem('trace-session-v1',session.session_id)}catch{/* The owner is also in the workspace reference. */}
    rememberMediaRecord({id:job.id,owner:session.session_id})
    writeMediaCache({job:{id:job.id,owner:session.session_id},classIds:[],draftId:null,time:time.value,target:selected.value,panel:'chat'})
    location.hash='#assistant'
  }catch(e){error.value=errorText(e)}
  finally{opening.value=false}
}
watch(()=>props.demoId,()=>{save();void load()},{immediate:true})
watch([selected,time],save)
onScopeDispose(()=>{save();alive=false;++generation;player.value?.pause()})
</script>

<template>
  <div class="media-page demo-page" :class="{ 'has-result':demo }">
    <header class="workspace-heading"><div><p class="workspace-eyebrow">视迹 / {{offlineExamples?'离线案例':'视频案例'}}</p><h1>{{ demo?.title || '视频案例' }}</h1><p class="workspace-subtitle">选择问题或编号，回到画面核对。</p></div><a v-if="!offlineExamples" class="media-secondary" href="#assistant"><Icon name="upload" :size="16" />上传自己的素材</a></header>
    <nav class="demo-switcher" aria-label="选择视频案例"><a v-for="(item,index) in demos" :key="item.id" :href="demoHref(item.id)" :aria-current="demoId===item.id?'page':undefined"><span>0{{index+1}}</span>{{item.focus}}</a></nav>
    <p v-if="loading" class="demo-status" role="status">正在载入已完成的识别结果…</p>
    <div v-else-if="!demo" class="demo-status" role="alert"><p>{{error || '案例暂时无法读取。'}}</p><button class="media-secondary" @click="load">重新载入</button></div>
    <template v-else>
      <div class="workspace-mobile-tabs" role="tablist" aria-label="切换案例面板"><button role="tab" :aria-selected="panel==='media'" @click="panel='media'">画面与编号</button><button role="tab" :aria-selected="panel==='chat'" @click="panel='chat'">示例解读</button></div>
      <div class="workspace-shell has-result" :data-mobile-pane="panel">
        <section ref="mediaPanel" class="workspace-media-panel demo-media" aria-label="案例画面和识别目标">
          <header class="workspace-media-toolbar"><div><h2>{{demo.focus}}</h2><p>{{demo.duration.toFixed(1)}}秒 · {{demo.result.counts.length}}种识别类别</p></div><span class="workspace-phase complete">预先分析完成</span></header>
          <MediaDetectionViewer :key="demo.id+demo.version" ref="player" :result="demo.result" :selected-target="selected" :initial-time="time" @time="time=$event" @select="chooseTarget" @error="playbackError=true" />
          <p v-if="playbackError" class="media-error-text media-inline-status" role="alert">视频暂时无法播放，可先查看右侧的证据截图。</p>
          <div class="media-targets"><div class="media-section-label"><h2>选择一个物体回看</h2><span>类别颜色与编号对应</span></div><div class="media-target-list"><button v-for="target in demo.result.targets.slice(0,6)" :key="target.id" :aria-pressed="selected===target.id" @click="chooseTarget(target.id)"><i class="media-type-dot" :style="{background:classColor(target.label)}"></i>{{target.label_name}} #{{target.id}}</button><details v-if="demo.result.targets.length>6"><summary>查看其余编号</summary><div><button v-for="target in demo.result.targets.slice(6)" :key="target.id" :aria-pressed="selected===target.id" @click="chooseTarget(target.id)"><i class="media-type-dot" :style="{background:classColor(target.label)}"></i>{{target.label_name}} #{{target.id}}</button></div></details></div><p v-if="selectedObject" class="media-target-caption">正在查看{{selectedObject.label_name}} #{{selectedObject.id}}。画面下方可取消“只看选中的物体”。</p></div>
          <div class="media-result-footnote"><p>编号用于对应本段视频中的识别记录。遮挡、漏检或关联不确定时，记录可能中断或重新编号。</p><a :href="demo.result.media_url" download><Icon name="download" :size="15" />保存标注视频</a></div>
        </section>
        <aside class="media-conversation demo-conversation" aria-label="案例结果与示例解读">
          <div class="media-summary"><h2>识别结果</h2><p class="media-summary-headline">{{demo.subtitle}}</p><div class="media-counts"><span v-for="row in demo.result.counts" :key="row.label">{{row.name}}<b>最多 {{row.max_simultaneous}}</b></span></div><p class="demo-count-note">各类别在单个采样画面中最多检出的数量。</p></div>
          <div class="media-chat-heading"><h2>点一个问题，看看依据</h2></div>
          <div class="demo-questions"><button v-for="(item,index) in demo.guides" :key="item.id" :aria-pressed="guideIndex===index" @click="chooseGuide(index)">{{item.question}}<Icon name="chevron" :size="15" /></button></div>
          <article v-if="guide" class="demo-answer" aria-live="polite"><p class="demo-answer-label">基于已保存的识别记录</p><p>{{guide.answer}}</p><div class="media-answer-shots"><button v-for="item in guide.citations" :key="item.id" @click="proof(item)"><img :src="item.image_url" :alt="item.description" width="160" height="90" loading="lazy" /><span>回看 {{timeLabel(item.t)}}</span></button></div></article>
          <div v-if="!offlineExamples" class="demo-live"><button class="media-primary" :disabled="opening || !health?.live_agent || !health?.capabilities?.local_uploads" @click="continueAsking">{{opening?'正在保留案例…':'继续自由提问'}}<Icon name="arrow" :size="16" /></button><p v-if="!health?.live_agent || !health?.capabilities?.local_uploads">暂时无法继续提问，可先查看示例问题和对应画面。</p></div>
          <p v-if="error" class="media-error-text demo-error" role="alert">{{error}}</p>
        </aside>
      </div>
      <p class="demo-source">素材：{{demo.source.author}} · <a :href="demo.source.url" target="_blank" rel="noopener noreferrer">原始来源</a> · <a :href="demo.source.license_url" target="_blank" rel="noopener noreferrer">{{demo.source.license}}</a></p>
    </template>
  </div>
</template>

<style scoped>
.demo-page .workspace-heading{min-width:0}
@media(max-width:600px){.demo-page .workspace-heading{flex-direction:column;gap:14px}}
.demo-conversation{height:auto;min-height:0;max-height:none}
.demo-switcher{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}.demo-switcher a{display:flex;align-items:center;gap:10px;min-height:46px;padding:10px 16px;border:1px solid #dce3ee;border-radius:7px;background:#fff;font-size:13px;color:#52647d;text-decoration:none}.demo-switcher span{font-size:11px;color:#7c8da7}.demo-switcher a[aria-current=page]{color:#3159df;border-color:#9cb2f4;background:#f1f5ff}.demo-status{padding:36px 0;color:#62748c}.demo-page .workspace-heading>a{display:inline-flex;align-items:center;gap:8px;text-decoration:none;white-space:nowrap}.demo-conversation{padding-bottom:0}.demo-questions{display:grid;gap:8px;margin:0 20px 18px}.demo-questions button{display:flex;align-items:center;justify-content:space-between;gap:8px;text-align:left;min-height:46px;padding:10px 12px;background:#fff;border:1px solid #e1e6ef;border-radius:6px;color:#52647d;font-size:13px;cursor:pointer}.demo-questions button[aria-pressed=true]{background:#f1f5ff;border-color:#a7baf2;color:#3159df}.demo-answer{padding:0 20px 23px;font-size:14px;line-height:1.9;color:#35445b}.demo-answer>p{white-space:pre-line}.demo-answer-label,.demo-count-note{font-size:11px;color:#748197;line-height:1.8}.demo-live{padding:18px 20px;border-top:1px solid #e6ebf2}.demo-live>p{font-size:11px;line-height:1.85;color:#748197;margin:12px 0 0}.demo-source{font-size:11px;line-height:1.9;color:#748197;margin:20px 0}.demo-source a{color:#526d9d}.demo-error{margin:0 20px 18px}.demo-page a:focus-visible,.demo-page button:focus-visible,.demo-page summary:focus-visible{outline:3px solid #91aafd;outline-offset:3px}@media(max-width:600px){.demo-switcher{gap:7px}.demo-switcher a{font-size:12px;padding:9px 11px}.demo-page .workspace-heading{align-items:start}.demo-page .workspace-heading h1{font-size:22px}.demo-page .workspace-heading>a{font-size:11px;padding:9px}.demo-page .workspace-mobile-tabs{margin-bottom:16px}.demo-answer{font-size:14px}}
</style>
