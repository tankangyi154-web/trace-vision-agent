import { computed, onScopeDispose, ref } from 'vue'
import { api, errorText } from '../api'
import type { InvestigationCase, ReviewJob } from '../types'

const STORAGE_KEY = 'trace-investigation-review-v1'
function readSaved(): { request_id: string | null; review_id: string | null; request_pending: boolean } {
  try {
    const value = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null')
    return { request_id: typeof value?.request_id === 'string' ? value.request_id : null, review_id: typeof value?.review_id === 'string' ? value.review_id : null, request_pending: value?.request_pending === true }
  } catch { return { request_id: null, review_id: null, request_pending: false } }
}

export function useInvestigation() {
  const saved = readSaved()
  const caseData = ref<InvestigationCase | null>(null)
  const review = ref<ReviewJob | null>(null)
  const threshold = ref(5)
  const loading = ref(false)
  const submitting = ref(false)
  const polling = ref(false)
  const error = ref('')
  const reviewId = ref<string | null>(saved.review_id)
  const requestPending = ref(saved.request_pending)
  let requestId = saved.request_id
  let loadVersion = 0
  let pollVersion = 0
  let alive = true
  let timer: ReturnType<typeof setTimeout> | undefined
  let wake: (() => void) | undefined
  const reviewBusy = computed(() => submitting.value || polling.value || review.value?.status === 'queued' || review.value?.status === 'running')
  const canRun = computed(() => !!caseData.value?.review_available && !reviewBusy.value && !loading.value)

  function persist() {
    if (!alive) return
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ request_id: requestId, review_id: reviewId.value, request_pending: requestPending.value })) } catch { /* Live API state remains authoritative if tab storage is unavailable. */ }
  }
  function stopPolling() {
    pollVersion += 1
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
    wake?.(); wake = undefined
    polling.value = false
  }
  onScopeDispose(() => { alive = false; loadVersion += 1; stopPolling() })
  function accept(job: ReviewJob) {
    review.value = job
    reviewId.value = job.review_id
    requestPending.value = false
    persist()
  }
  async function readReview(id: string, value: number) {
    return api<ReviewJob>(`/api/investigation/reviews/${encodeURIComponent(id)}?threshold=${value}`)
  }
  async function follow(id: string) {
    stopPolling()
    const version = pollVersion
    const value = threshold.value
    polling.value = true
    const deadline = Date.now() + 180_000
    try {
      while (alive && version === pollVersion) {
        await new Promise<void>(resolve => { wake = resolve; timer = setTimeout(() => { timer = undefined; wake = undefined; resolve() }, 1200) })
        if (!alive || version !== pollVersion) return
        const job = await readReview(id, value)
        if (!alive || version !== pollVersion) return
        accept(job)
        if (job.status === 'complete' || job.status === 'failed') return
        if (Date.now() > deadline) { error.value = '本地任务尚未返回最终结果。可以重新连接原复核任务。'; return }
      }
    } catch (e) { if (alive && version === pollVersion) error.value = errorText(e) }
    finally { if (version === pollVersion) polling.value = false }
  }

  async function load(value = threshold.value, preferredReviewId?: string) {
    const version = ++loadVersion
    stopPolling()
    loading.value = true
    error.value = ''
    try {
      const nextCase = await api<InvestigationCase>(`/api/investigation?threshold=${value}`)
      const id = preferredReviewId || reviewId.value || (!requestPending.value ? nextCase.latest_review_id : null)
      const nextReview = id ? await readReview(id, value) : null
      if (!alive || version !== loadVersion) return
      caseData.value = nextCase
      threshold.value = value
      review.value = nextReview
      if (nextReview) accept(nextReview)
      if (nextReview?.status === 'queued' || nextReview?.status === 'running') void follow(nextReview.review_id)
    } catch (e) { if (alive && version === loadVersion) error.value = errorText(e) }
    finally { if (version === loadVersion) loading.value = false }
  }
  async function setThreshold(value: 3 | 5) { await load(value) }
  async function startReview() {
    if (!canRun.value) return
    submitting.value = true
    error.value = ''
    if (!requestPending.value || !requestId) requestId = crypto.randomUUID()
    requestPending.value = true
    reviewId.value = null
    review.value = null
    persist()
    try {
      const posted = await api<ReviewJob>('/api/investigation/reviews', { method: 'POST', body: JSON.stringify({ request_id: requestId }) })
      if (!alive) return
      reviewId.value = posted.review_id
      persist()
      // POST has no threshold parameter. Always obtain the selected threshold's
      // facts before showing a comparison, even if that POST already completed.
      const job = await readReview(posted.review_id, threshold.value)
      if (!alive) return
      accept(job)
      if (job.status === 'queued' || job.status === 'running') void follow(job.review_id)
    } catch (e) { if (alive) error.value = errorText(e) }
    finally { submitting.value = false }
  }
  async function reconnect() { if (reviewId.value) await load(threshold.value, reviewId.value); else await startReview() }

  return { caseData, review, reviewId, threshold, loading, submitting, polling, reviewBusy, canRun, requestPending, error, load, setThreshold, startReview, reconnect }
}
