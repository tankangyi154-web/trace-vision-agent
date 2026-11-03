import { computed, ref, type Ref } from 'vue'
import type { ChatContext, InvestigationCase } from '../types'

export function useReviewChatContext(threshold: Ref<number>, caseData: Ref<Pick<InvestigationCase, 'id'> | null>) {
  // Visible historical evidence is not an explicit choice for this model task.
  // Start fresh; only the manual-review action may bind a review to this scope.
  const manualReviewId = ref<string | null>(null)
  const chatContext = computed<ChatContext>(() => ({
    scene_id: 'harbor', zone_id: 'A', dwell_seconds: threshold.value,
    investigation_id: caseData.value?.id || 'harbor-T001-gap', review_id: manualReviewId.value,
  }))
  function bindManualReview(id: string) { manualReviewId.value = id }
  return { chatContext, bindManualReview }
}
