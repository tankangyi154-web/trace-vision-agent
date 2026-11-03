<script setup lang="ts">
import Icon from './Icon.vue'
import { sceneHref, demoHref } from '../navigation'
import { demoPoster } from '../demoPosters'
import type { GalleryItem } from '../preparedDemos'

defineProps<{ scenes: GalleryItem[]; loading: boolean; error: string; prepared?: boolean }>()
defineEmits<{ retry: [] }>()
const descriptions: Record<string, string> = {
  harbor: '从船舶进出与出现记录定位片段，核对画面并留下说明。',
  crossing: '查看车辆在范围内的出现时长，回看对应片段。',
  night: '查看夜间看不清的片段，核对哪些结论还不能确定。',
}
</script>

<template>
  <nav v-if="scenes.length" class="scene-gallery" aria-label="视频演示案例">
    <a v-for="(item, index) in scenes" :key="item.id" :href="prepared ? demoHref(item.id) : sceneHref(item.id)" :aria-label="`打开${item.title}案例`">
      <img :src="demoPoster(item.id, item.poster_url)" :alt="`${item.title}的实际分析画面`" width="960" height="540" loading="lazy" />
      <div><span>{{ String(index + 1).padStart(2, '0') }} / {{ item.focus }}</span><h3>{{ item.title }}</h3><p>{{ prepared ? item.subtitle : descriptions[item.id] || item.subtitle }}</p><Icon name="arrow" :size="17" /></div>
    </a>
  </nav>
  <p v-else-if="loading" class="gallery-status" role="status">正在读取视频案例…</p>
  <div v-else class="gallery-status" role="status"><p>{{ error || '视频案例暂时没有载入。' }}</p><button type="button" @click="$emit('retry')">重新载入案例</button></div>
</template>

<style scoped>
.scene-gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.scene-gallery>a{display:flex;flex-direction:column;overflow:hidden;border:1px solid #dfe6f0;border-radius:8px;text-decoration:none;color:var(--ink);background:white;transition:border-color .16s}.scene-gallery>a:hover{border-color:#7293ed}.scene-gallery img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:cover;background:#e9eef5}.scene-gallery>a>div{position:relative;flex:1;min-height:184px;padding:22px 22px 48px}.scene-gallery span{display:block;font-size:12px;color:#6b7d97;margin-bottom:10px}.scene-gallery h3{font-size:17px;line-height:1.8;font-weight:550;margin:0}.scene-gallery p{font-size:13px;color:#69778c;line-height:1.9;margin:12px 18px 0 0}.scene-gallery svg{position:absolute;bottom:18px;right:22px;color:#3159df}.gallery-status{font-size:14px;color:#69778c;line-height:1.9;padding:20px 0}.gallery-status button{min-height:44px;border:1px solid #dfe6f0;border-radius:6px;background:white;padding:8px 15px;color:#3159df;cursor:pointer}.scene-gallery a:focus-visible,.gallery-status button:focus-visible{outline:3px solid #91aafd;outline-offset:4px}@media(max-width:900px){.scene-gallery{gap:12px}.scene-gallery>a>div{padding:19px 17px 45px}.scene-gallery h3{font-size:16px}}@media(max-width:650px){.scene-gallery{grid-template-columns:1fr;gap:16px}.scene-gallery>a>div{min-height:0;padding:20px 20px 45px}.scene-gallery p{font-size:14px}.scene-gallery h3{font-size:17px}}
</style>
