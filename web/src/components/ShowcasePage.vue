<script setup lang="ts">
import { computed, ref } from 'vue'
import { offlineExamples } from '../buildMode'
import Icon from './Icon.vue'
import SceneGallery from './SceneGallery.vue'
import type { Health } from '../types'
import type { GalleryItem } from '../preparedDemos'

const props = defineProps<{ health: Health | null; scenes: GalleryItem[]; loading: boolean; error: string }>()
defineEmits<{ retry: [] }>()
const visualReady = computed(() => props.health?.capabilities?.video_analysis)
const caseSection = ref<HTMLElement | null>(null)
const caseTitle = ref<HTMLElement | null>(null)
function showCases() {
  caseTitle.value?.focus({ preventScroll: true })
  caseSection.value?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
}
</script>

<template>
  <div class="showcase-page">
    <section class="showcase-hero" aria-labelledby="showcase-title">
      <div class="showcase-copy"><p class="showcase-eyebrow">TRACE / 视觉证据分析</p><h1 id="showcase-title">看见结果，<br />也能核对依据。</h1><p class="showcase-description">把图片与短视频中的目标、时间和观测缺口，变成可查询、可回看的证据。</p>
        <div class="showcase-actions"><button class="showcase-primary" type="button" @click="showCases">选择演示案例 <Icon name="arrow" :size="18" /></button><a v-if="!offlineExamples" class="showcase-secondary" href="#assistant">上传自己的素材 <Icon name="upload" :size="17" /></a></div>
        <p class="showcase-status" aria-live="polite"><span>{{ health ? (visualReady ? '可上传图片与视频' : '先从已有案例开始体验') : '正在读取运行状态' }}</span><span>{{ health?.live_agent ? '可以继续提问' : '已有案例可直接查看' }}</span></p>
      </div>
      <button type="button" class="showcase-preview" aria-label="查看三个视频演示案例" @click="showCases"><img v-if="scenes[0]" :src="scenes[0].poster_url" alt="白天街景的实际多类别识别结果" width="960" height="540" /><span class="showcase-preview-note"><span>三个真实视频案例</span><strong>白天看类别，夜间看表现，<br />交错时沿编号回看。</strong><span class="showcase-preview-link">查看全部案例 <Icon name="arrow" :size="16" /></span></span></button>
    </section>

    <section ref="caseSection" class="showcase-cases" aria-labelledby="cases-title"><div class="showcase-section-heading"><div><p class="showcase-eyebrow">选一个场景开始</p><h2 id="cases-title" ref="caseTitle" tabindex="-1">三个视频案例</h2></div><a v-if="!offlineExamples" href="#implementation">查看技术原理 <Icon name="arrow" :size="16" /></a></div>
      <SceneGallery :scenes="scenes" :loading="loading" :error="error" prepared @retry="$emit('retry')" />
    </section>


    <section class="showcase-principles" aria-labelledby="principles-title"><div><p class="showcase-eyebrow">实现的重点</p><h2 id="principles-title">从观测到回答，每一步都有边界。</h2></div><dl><div><dt>事实由工具计算</dt><dd>数量、时间和驻留来自结构化观测，模型组织查询与解释。</dd></div><div><dt>回答可以回看</dt><dd>引用绑定实际取回的证据；缺帧和身份关联不确定性会保留。</dd></div><div><dt>执行有明确预算</dt><dd>每次最多三次模型调用、五次工具执行，任务隔离并控制临时素材保留期。</dd></div></dl><p v-if="offlineExamples">离线案例版：可直接播放、筛选类型和回看证据。上传自己的素材及自由提问请使用本地分析版。</p><a v-else href="#source">查看源码与复现说明 <Icon name="arrow" :size="16" /></a></section>
  </div>
</template>

<style scoped>
.showcase-page{max-width:1190px;margin:0 auto;padding:52px 32px 30px;color:var(--ink)}.showcase-hero{display:grid;grid-template-columns:1fr 1fr;gap:54px;align-items:center}.showcase-eyebrow{font-size:11px;letter-spacing:.14em;color:#64738a;margin:0 0 15px}.showcase-copy h1{font-size:clamp(36px,4.4vw,58px);letter-spacing:-.04em;line-height:1.28;font-weight:650;margin:0}.showcase-description{max-width:410px;font-size:16px;color:#617087;line-height:1.9;margin:24px 0}.showcase-actions{display:flex;gap:12px;flex-wrap:wrap}.showcase-actions a,.showcase-actions button{display:inline-flex;align-items:center;justify-content:center;gap:9px;min-height:46px;padding:12px 17px;border-radius:7px;font-size:13px;text-decoration:none}.showcase-primary{border:0;background:#3159df;color:white;font:inherit;cursor:pointer}.showcase-secondary{border:1px solid #dce2ec;background:white;color:#34435a}.showcase-status{display:flex;gap:12px;flex-wrap:wrap;color:#67768b;font-size:10px;margin:18px 0 0}.showcase-status span{display:inline-flex;align-items:center;gap:5px}.showcase-status span:before{content:'';width:5px;height:5px;background:#779b85;border-radius:50%}.showcase-preview{position:relative;display:block;overflow:hidden;border-radius:12px;background:#16293c;min-height:335px;width:100%;border:0;padding:0;text-align:left;font:inherit;color:white;text-decoration:none;cursor:pointer}.showcase-preview>img{display:block;width:100%;height:335px;object-fit:cover;opacity:.66}.showcase-preview:after{content:'';position:absolute;inset:0;background:linear-gradient(0deg,#10283de8,transparent 85%)}.showcase-preview-note{position:absolute;inset:auto 25px 24px;z-index:1;display:grid;gap:12px}.showcase-preview-note>span:first-child{font-size:11px;color:#d8e4ef}.showcase-preview-note strong{font-size:23px;font-weight:550;line-height:1.6}.showcase-preview-link{display:flex;align-items:center;gap:9px;font-size:12px;color:#e0eaff}.showcase-cases{margin-top:54px;scroll-margin-top:24px}.showcase-section-heading{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-bottom:22px}.showcase-section-heading .showcase-eyebrow{margin-bottom:8px}.showcase-section-heading h2,.showcase-principles h2{font-size:23px;font-weight:600;line-height:1.5;margin:0}.showcase-section-heading>a,.showcase-principles>a{display:inline-flex;align-items:center;gap:8px;min-height:44px;font-size:12px;text-decoration:none;white-space:nowrap}.showcase-principles{border-top:1px solid #e0e6ef;margin-top:58px;padding-top:34px}.showcase-principles dl{display:grid;grid-template-columns:repeat(3,1fr);gap:28px;margin:25px 0 12px}.showcase-principles dt{font-size:14px;font-weight:550;margin-bottom:8px}.showcase-principles dd{font-size:12px;line-height:1.9;color:#69758a;margin:0}.showcase-page a:focus-visible,.showcase-page button:focus-visible,.showcase-page summary:focus-visible{outline:3px solid #91aafd;outline-offset:4px}@media(max-width:900px){.showcase-page{padding:34px 24px}.showcase-hero{gap:25px}.showcase-copy h1{font-size:39px}.showcase-description{font-size:14px}}@media(max-width:650px){.showcase-page{padding:28px 18px 12px}.showcase-hero{grid-template-columns:1fr;gap:28px}.showcase-copy h1{font-size:40px}.showcase-description{font-size:14px;margin:19px 0}.showcase-actions a,.showcase-actions button{font-size:12px;flex:1;padding:12px}.showcase-status{font-size:10px;gap:10px}.showcase-preview{min-height:255px}.showcase-preview>img{height:255px}.showcase-preview-note{inset:auto 21px 20px}.showcase-preview-note strong{font-size:20px}.showcase-cases{margin-top:38px}.showcase-section-heading{align-items:start;flex-direction:column;gap:7px}.showcase-section-heading h2,.showcase-principles h2{font-size:21px}.showcase-principles{margin-top:38px;padding-top:27px}.showcase-principles dl{grid-template-columns:1fr;gap:18px}.showcase-principles dd{font-size:14px}}
</style>
