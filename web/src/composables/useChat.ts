import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import { api, ApiError, errorText } from '../api'
import { mediaWaitMs } from '../mediaPolicy'
import type { ChatContext, ChatMessage, ChatRequest, ChatResult, Health, Session } from '../types'

const SESSION_KEY = 'trace-session-v1'
const CACHE_KEY = 'trace-chat-v1'
const MAX_SCOPES = 6
const MAX_MESSAGES = 8
type Context = ChatContext
type History = Record<string, ChatMessage[]>
type Cache = { session_id: string | null; pending: ChatRequest | null; remaining: number | null; histories: History }
function scopeKey(context: Context): string {
  const parts: (string | number | null)[] = [context.scene_id, context.zone_id, context.dwell_seconds]
  if (context.investigation_id || context.review_id) parts.push(context.investigation_id || null, context.review_id || null)
  return JSON.stringify(parts)
}
function readSession(): string | null {
  try { const id = localStorage.getItem(SESSION_KEY); if (id) return id } catch { /* Fall back to the current browser tab. */ }
  try { const id = JSON.parse(sessionStorage.getItem(CACHE_KEY) || 'null')?.session_id; return typeof id === 'string' ? id : null } catch { return null }
}
function validRequest(value: unknown): value is ChatRequest {
  if (!value || typeof value !== 'object') return false
  const request = value as Record<string, unknown>
  return ['request_id', 'session_id', 'scene_id', 'zone_id', 'question'].every(key => typeof request[key] === 'string' && (request[key] as string).length > 0 && (request[key] as string).length <= 500)
    && typeof request.dwell_seconds === 'number' && Number.isFinite(request.dwell_seconds) && request.dwell_seconds > 0
}
function trimHistories(histories: History): History {
  return Object.fromEntries(Object.entries(histories).slice(-MAX_SCOPES).map(([key, messages]) => [key, messages.slice(-MAX_MESSAGES)]))
}
function readCache(sessionId: string | null): Cache {
  const empty: Cache = { session_id: sessionId, pending: null, remaining: null, histories: {} }
  try {
    const raw = sessionStorage.getItem(CACHE_KEY)
    if (!raw || raw.length > 1_000_000) return empty
    const data = JSON.parse(raw)
    if (!data || data.session_id !== sessionId || !data.histories || typeof data.histories !== 'object') return empty
    const histories = Object.fromEntries(Object.entries(data.histories).filter(([key, value]) => key.length < 300 && Array.isArray(value)).map(([key, value]) => [key, (value as ChatMessage[]).filter(item => item && typeof item.id === 'string' && typeof item.question === 'string')]))
    return {
      session_id: sessionId,
      pending: validRequest(data.pending) && data.pending.session_id === sessionId ? data.pending : null,
      remaining: Number.isInteger(data.remaining) && data.remaining >= 0 ? data.remaining : null,
      histories: trimHistories(histories),
    }
  } catch { return empty }
}

export function useChat(health: Ref<Health | null>, context: Ref<Context>, restoredOwner?: string) {
  const sessionId = ref<string | null>(readSession() || restoredOwner || null)
  let mediaOwner = restoredOwner || ''
  const cached = readCache(sessionId.value)
  const histories = ref<History>(cached.histories)
  const pending = ref<ChatRequest | null>(cached.pending)
  const messages = computed(() => histories.value[scopeKey(context.value)] || [])
  const question = ref('')
  const busy = ref(false)
  const remaining = ref<number | null>(cached.remaining)
  const status = ref('')
  const connectionError = ref('')
  const storageAvailable = ref(true)
  const expiredScene = ref('')
  const forgottenScenes = new Set<string>()
  const canAsk = computed(() => !!health.value?.live_agent && remaining.value !== 0 && !busy.value && !pending.value && !!context.value.scene_id)
  const canRetry = computed(() => !!pending.value && !busy.value)
  const pendingInCurrentScope = computed(() => !!pending.value && scopeKey(pending.value) === scopeKey(context.value))
  let alive = true
  let stopPostPolling: (() => void) | null = null
  onScopeDispose(() => { alive = false; stopPostPolling?.() })

  function persist() {
    if (!alive) return
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ session_id: sessionId.value, pending: pending.value, remaining: remaining.value, histories: trimHistories(histories.value) }))
      storageAvailable.value = true
    } catch { storageAvailable.value = false }
  }
  watch([histories, pending, remaining, sessionId], persist, { deep: true, flush: 'sync' })
  watch(() => scopeKey(context.value), () => { question.value = ''; connectionError.value = '' })

  function upsert(request: ChatRequest, result?: ChatResult, error?: string) {
    if (!alive || forgottenScenes.has(request.scene_id)) return
    const key = scopeKey(request)
    const history = [...(histories.value[key] || [])]
    const index = history.findIndex(item => item.id === request.request_id)
    const message: ChatMessage = { id: request.request_id, question: request.question, ...(result ? { result } : {}), ...(error ? { error } : {}) }
    if (index < 0) history.push(message)
    else history[index] = message
    // Recently touched scopes are inserted last, bounding storage independently of configurable quotas.
    const next = { ...histories.value }
    delete next[key]
    next[key] = history.slice(-MAX_MESSAGES)
    histories.value = trimHistories(next)
  }

  function forgetScene(sceneId: string) {
    forgottenScenes.add(sceneId)
    histories.value = Object.fromEntries(Object.entries(histories.value).filter(([key]) => {
      try { return JSON.parse(key)[0] !== sceneId } catch { return true }
    }))
    if (pending.value?.scene_id === sceneId) pending.value = null
    question.value = ''; connectionError.value = ''
    persist()
  }
  if (pending.value) {
    const existing = histories.value[scopeKey(pending.value)]?.find(item => item.id === pending.value?.request_id)
    upsert(pending.value, existing?.result, existing?.error)
  }

  async function ensureSession(forceNew = false): Promise<string> {
    if (forceNew) { sessionId.value = null; pending.value = null; remaining.value = null; histories.value = {}; try { localStorage.removeItem(SESSION_KEY) } catch { /* Storage is optional. */ } }
    if (sessionId.value) return sessionId.value
    const session = await api<Session>('/api/sessions', { method: 'POST', body: '{}' })
    histories.value = {}
    sessionId.value = session.session_id
    remaining.value = session.remaining
    try { localStorage.setItem(SESSION_KEY, session.session_id) } catch { /* Private browser storage may be disabled. */ }
    return session.session_id
  }

  function accept(result: ChatResult, request: ChatRequest) {
    if (!alive || result.request_id !== request.request_id) return
    remaining.value = result.remaining
    status.value = result.stage
    upsert(request, result)
    if (result.status === 'complete' || result.status === 'failed') pending.value = null
  }
  async function awaitResult(initial: ChatResult, request: ChatRequest) {
    let result = initial
    accept(result, request)
    const deadline = Date.now() + 150_000 + (request.scene_id.startsWith('upload-') ? mediaWaitMs : 0)
    while (alive && (result.status === 'queued' || result.status === 'running')) {
      if (Date.now() > deadline) throw new Error('The request is still pending.')
      await new Promise(resolve => setTimeout(resolve, 1200))
      if (!alive) return
      result = await api<ChatResult>(`/api/requests/${encodeURIComponent(request.request_id)}`, { headers: { 'X-Session-ID': request.session_id } })
      accept(result, request)
    }
  }

  async function postWithStatus(request: ChatRequest) {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let wake: (() => void) | undefined
    const controller = new AbortController()
    let resolvePolled!: (result: ChatResult | null) => void
    const polledTerminal = new Promise<ChatResult | null>(resolve => { resolvePolled = resolve })
    const stop = () => {
      if (!active) return
      active = false
      if (timer !== undefined) clearTimeout(timer)
      wake?.()
      wake = undefined
      controller.abort()
      resolvePolled(null)
    }
    stopPostPolling = stop

    // The POST keeps the Vercel function alive; this side channel only reads
    // recorded stages and never submits another execution, including on 404.
    void (async () => {
      while (active && alive) {
        await new Promise<void>(resolve => {
          wake = resolve
          timer = setTimeout(() => { timer = undefined; wake = undefined; resolve() }, 1200)
        })
        if (!active || !alive) return
        try {
          const result = await api<ChatResult>(`/api/requests/${encodeURIComponent(request.request_id)}`, { headers: { 'X-Session-ID': request.session_id }, signal: controller.signal })
          if (!active || !alive) return
          if (result.request_id !== request.request_id) continue
          accept(result, request)
          if (result.status === 'complete' || result.status === 'failed') {
            resolvePolled(result)
            stop()
            return
          }
        } catch {
          // Reservation may not exist yet, or the read path may be temporarily
          // unavailable. The original POST remains the execution authority.
        }
      }
    })()

    const submitted = api<ChatResult>('/api/chat', { method: 'POST', body: JSON.stringify(request),
      ...(request.scene_id.startsWith('upload-') && mediaOwner ? { headers: { 'X-Media-Owner': mediaOwner } } : {}) }).then(
      result => ({ kind: 'post' as const, result }),
      error => ({ kind: 'error' as const, error }),
    )
    try {
      const outcome = await Promise.race([submitted, polledTerminal.then(result => ({ kind: 'polled' as const, result }))])
      stop()
      if (outcome.kind === 'error') throw outcome.error
      if (outcome.kind === 'post') await awaitResult(outcome.result, request)
      // A polled terminal result has already been accepted. A late POST result
      // or transport error is deliberately not allowed to overwrite it.
    } finally {
      stop()
      if (stopPostPolling === stop) stopPostPolling = null
    }
  }

  function handleRequestError(error: unknown, request?: ChatRequest) {
    if (!alive) return
    connectionError.value = errorText(error)
    if (error instanceof ApiError) {
      // Classify by the API's reason, not just its HTTP status. A missing scene
      // is not an expired session, and an unknown storage/gateway error may
      // arrive after execution and must retain the original request id.
      const rejected = ['session_not_found', 'session_limit', 'daily_limit', 'request_conflict', 'scene_not_found', 'invalid_zone', 'not_configured'].includes(error.code)
      const expiredUpload = error.code === 'not_found' && request?.scene_id.startsWith('upload-')
      if (rejected || expiredUpload || error.status === 400 || error.status === 422) pending.value = null
      if (expiredUpload) expiredScene.value = request!.scene_id
      if (error.code === 'session_not_found') {
        sessionId.value = null
        remaining.value = null
        try { localStorage.removeItem(SESSION_KEY) } catch { /* Storage is optional. */ }
        connectionError.value = '原请求无法恢复：会话已过期。可以明确提交新问题开始新会话；不会自动重发旧问题。'
        status.value = '原请求无法恢复，会话已过期'
      }
      if (error.code === 'session_limit') remaining.value = 0
    }
    if (request) upsert(request, undefined, connectionError.value)
  }

  async function send(text = question.value) {
    if (!canAsk.value || !text.trim()) return
    const requestedContext = { ...context.value }
    const trimmed = text.trim().slice(0, 500)
    busy.value = true
    connectionError.value = ''
    status.value = '请求已发送，等待服务端响应'
    let request: ChatRequest | undefined
    try {
      const session_id = await ensureSession()
      if (!alive) return
      request = { ...requestedContext, request_id: crypto.randomUUID(), session_id, question: trimmed }
      pending.value = request
      upsert(request)
      question.value = ''
      await postWithStatus(request)
    } catch (error) {
      handleRequestError(error, request)
    } finally { busy.value = false }
  }

  async function reconnect() {
    const request = pending.value
    if (!request || busy.value) return
    busy.value = true
    connectionError.value = ''
    status.value = '正在查询原请求状态'
    try {
      let result: ChatResult
      try {
        result = await api<ChatResult>(`/api/requests/${encodeURIComponent(request.request_id)}`, { headers: { 'X-Session-ID': request.session_id } })
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404 || error.code !== 'not_found') throw error
        // Explicit reconnect reuses the exact saved payload, never creates a fresh id.
        await postWithStatus(request)
        return
      }
      await awaitResult(result, request)
    } catch (error) {
      handleRequestError(error, request)
    } finally { busy.value = false }
  }

  return { messages, question, busy, remaining, pending, status, connectionError, canAsk, canRetry, pendingInCurrentScope, storageAvailable, send, reconnect, ensureSession, forgetScene, expiredScene,
    setMediaOwner: (owner: string) => { mediaOwner = owner } }
}
