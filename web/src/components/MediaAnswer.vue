<script setup lang="ts">
import { computed } from 'vue'
import { timeLabel } from '../api'
import type { ChatResult, Citation } from '../types'
const props = defineProps<{ reply: ChatResult; targets: { id: string; name: string }[]; kind: 'image' | 'video' }>()
const emit = defineEmits<{ citation: [Citation] }>()
const name = (citation: Citation) => props.targets.find(target => target.id === citation.track_id)?.name || '画面'
const proof = computed(() => props.reply.citations.filter((citation, index, all) => all.findIndex(other => other.track_id === citation.track_id) === index))
const state = (status: string) => status === 'confirmed' ? '画面记录' : status === 'interpretation' ? '画面解读' : '依据不足'
</script>

<template>
  <div class="media-chat-answer">
    <div v-if="reply.cache_hit" class="media-visual-context">已复用本机保存的回答</div>
    <div v-if="reply.visual_frame_count" class="media-visual-context">已查看 {{ reply.visual_frame_count }} 张目标画面</div>
    <p>{{ reply.answer }}</p>
    <template v-if="reply.answer_parts?.length">
      <div v-if="proof.length" class="media-proof-links"><button v-for="citation in proof" :key="citation.evidence_id" :data-target="citation.track_id" @click="emit('citation', citation)">看{{ name(citation) }}<span v-if="kind === 'video'"> · {{ timeLabel(citation.t) }}</span></button></div>
      <details class="media-answer-detail"><summary>查看依据与逐项说明</summary>
        <ul><li v-for="part in reply.answer_parts" :key="part.key"><span class="media-answer-kind" :class="part.status">{{ state(part.status) }}</span><p>{{ part.details || part.text }}</p></li></ul>
        <div v-if="reply.citations.length" class="media-answer-shots"><button v-for="(citation, i) in reply.citations" :key="citation.evidence_id" @click="emit('citation', citation)"><img :src="citation.image_url" width="128" height="72" alt="回答依据的实际截图" loading="lazy" /><span>{{ kind === 'image' ? `查看画面${i + 1}` : `回看 ${timeLabel(citation.t)}` }}</span></button></div>
      </details>
    </template>
    <div v-else-if="reply.citations.length" class="media-answer-shots"><button v-for="(citation, i) in reply.citations" :key="citation.evidence_id" @click="emit('citation', citation)"><img :src="citation.image_url" width="128" height="72" alt="回答依据的实际截图" loading="lazy" /><span>{{ kind === 'image' ? `查看画面${i + 1}` : `回看 ${timeLabel(citation.t)}` }}</span></button></div>
  </div>
</template>

<style scoped>
.media-proof-links{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.media-proof-links button{min-height:44px;border:1px solid #dce4f3;border-radius:6px;background:#f8faff;color:#3155ae;padding:8px 11px;font:inherit;font-size:12px;cursor:pointer}.media-proof-links button:hover{background:#edf2ff}.media-proof-links button:focus-visible,.media-answer-detail summary:focus-visible{outline:3px solid #91aafd;outline-offset:2px}.media-answer-detail{margin-top:12px;border-top:1px solid #e7edf5;padding-top:8px}.media-answer-detail summary{min-height:44px;display:flex;align-items:center;font-size:13px;color:#47628c;cursor:pointer}.media-answer-detail summary::before{content:'▸';margin-right:7px}.media-answer-detail[open] summary::before{content:'▾'}.media-answer-detail ul{list-style:none;padding:0;margin:4px 0 16px}.media-answer-detail li{padding:12px 0;border-bottom:1px solid #edf1f7}.media-answer-detail li p{font-size:13px;line-height:1.9;margin:7px 0 0;white-space:pre-line}.media-answer-kind{font-size:12px;color:#47628c}.media-answer-kind.interpretation{color:#52668a}.media-answer-kind.insufficient{color:#8a5828}
</style>
