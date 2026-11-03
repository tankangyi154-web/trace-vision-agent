<script setup lang="ts">
import Icon from './Icon.vue'
defineProps<{ message: string; disabled?: boolean; retryable?: boolean; partial?: boolean }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <div class="assistant-issue" :role="partial ? 'status' : 'alert'"><Icon name="info" :size="17" /><div><strong>{{ partial ? '画面解读暂未完成' : '这次提问没有完成' }}</strong><p>{{ message }}</p><button v-if="retryable !== false" :disabled="disabled" @click="$emit('retry')"><Icon name="refresh" :size="14" />重新提问</button><span v-else class="assistant-issue-note">你可以继续查看当前识别结果。</span></div></div>
</template>
