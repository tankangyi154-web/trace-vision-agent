<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import Icon from './Icon.vue'
import { resolveObjectNames, type ObjectChoice } from '../objectSelection'
const props = defineProps<{ modelValue: number[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [number[]]; 'pending-change': [boolean] }>()
const choices = ref<ObjectChoice[]>([])
const manual = ref('')
const manualError = ref('')
const feedback = ref('')
const query = ref('')
const dialog = ref<HTMLDialogElement | null>(null)
const search = ref<HTMLInputElement | null>(null)
const loadError = ref(false)
const selected = computed(() => props.modelValue.map(id => choices.value.find(c => c.id === id)).filter(Boolean) as ObjectChoice[])
const matches = computed(() => choices.value.filter(c => `${c.name} ${c.label} ${(c.aliases || []).join(' ')}`.toLowerCase().includes(query.value.trim().toLowerCase())))
async function load() { try { loadError.value = false; choices.value = (await api<{ classes: ObjectChoice[] }>('/api/object-classes')).classes } catch { loadError.value = true } }
async function open() { if (props.disabled || !choices.value.length) return; query.value = ''; dialog.value?.showModal(); await nextTick(); search.value?.focus() }
function add() {
  if (props.disabled || !choices.value.length) return
  const resolved = resolveObjectNames(manual.value, choices.value, props.modelValue)
  manualError.value = resolved.error; feedback.value = resolved.notice
  if (!resolved.error) { emit('update:modelValue', resolved.ids); manual.value = '' }
}
function toggle(id: number) {
  if (props.disabled) return
  manualError.value = ''; feedback.value = ''
  if (props.modelValue.includes(id)) emit('update:modelValue', props.modelValue.filter(i => i !== id))
  else if (props.modelValue.length < 3) emit('update:modelValue', [...props.modelValue, id])
}
watch(manual, value => emit('pending-change', !!value.trim()))
onMounted(load)
</script>
<template>
  <fieldset class="class-picker" :disabled="disabled">
    <legend>想找什么？<span>{{ modelValue.length }} / 3</span></legend>
    <div class="class-token-control" :class="{ invalid: manualError }"><div v-if="selected.length" class="class-picker-selection"><button v-for="item in selected" :key="item.id" type="button" class="class-chip" :aria-label="`移除${item.name}`" @click="toggle(item.id)">{{ item.name }}<Icon name="close" :size="13" /></button></div><label for="class-manual" class="sr-only">输入要识别的物体</label><div class="class-manual-row"><input id="class-manual" v-model="manual" maxlength="120" placeholder="输入物体名称，回车添加…" autocomplete="off" :disabled="disabled || !choices.length" :aria-invalid="!!manualError" aria-describedby="class-input-help class-input-feedback" @keydown.enter="!$event.isComposing && add()" @input="manualError = ''; feedback = ''" /><button type="button" class="class-add" :disabled="disabled || !choices.length || !manual.trim()" aria-label="添加物体" title="添加物体" @click="add"><Icon name="arrow" :size="17" /></button></div></div>
    <div class="class-picker-tools"><button type="button" class="class-open" :disabled="disabled || !choices.length" @click="open">浏览可识别物体</button><span>最多3种</span></div>
    <p id="class-input-help">中英文均可，多个名称用逗号分隔。当前支持80种常见物体。</p>
    <p v-if="manualError" id="class-input-feedback" class="class-input-error" role="alert">{{ manualError }}</p><p v-else id="class-input-feedback" role="status">{{ feedback || (manual.trim() ? '请先回车或点击箭头，确认输入的物体。' : '') }}</p>
    <p v-if="loadError" role="alert">可选物体加载失败。<button type="button" class="media-link" @click="load">重试</button></p>
  </fieldset>
  <dialog ref="dialog" class="class-dialog" aria-labelledby="class-dialog-title" @click="($event.target === dialog) && dialog?.close()"><header><div><h2 id="class-dialog-title">选择要找的物体</h2><p>已选 {{ modelValue.length }} / 3<span v-if="modelValue.length === 3">，取消一个后可以更换</span></p></div><button class="media-icon-button" aria-label="关闭物体选择" @click="dialog?.close()"><Icon name="close" /></button></header><label for="class-search">搜索物体</label><input id="class-search" ref="search" v-model="query" placeholder="如汽车、猫、杯子" type="search" autocomplete="off" /><div class="class-options"><button v-for="item in matches" :key="item.id" :aria-pressed="modelValue.includes(item.id)" :disabled="disabled || (modelValue.length >= 3 && !modelValue.includes(item.id))" @click="toggle(item.id)">{{ item.name }}<Icon v-if="modelValue.includes(item.id)" name="check" :size="16" /></button><p v-if="!matches.length">暂不支持这个物体，试试其他名称。</p></div><footer><span>可选常见物体，最多3种</span><button class="media-primary" @click="dialog?.close()">完成选择</button></footer></dialog>

</template>
