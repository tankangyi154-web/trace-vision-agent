export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message) }
}

let offlineHandler: ((path: string, init: RequestInit) => Promise<unknown>) | null = null
export function installOfflineApi(handler: (path: string, init: RequestInit) => Promise<unknown>) { offlineHandler = handler }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (offlineHandler) return offlineHandler(path, init) as Promise<T>
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init.headers } })
  if (!response.ok) {
    let code = `HTTP_${response.status}`
    let message = `服务暂时无法响应（${response.status}），请稍后重试。`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail?.message) { message = body.detail.message; code = body.detail.code || code }
    } catch { /* An HTML gateway error must not be rendered as an answer. */ }
    if (code === 'not_configured') message = '暂时无法继续提问，请稍后再试。'
    throw new ApiError(response.status, code, message)
  }
  return response.json() as Promise<T>
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.name === 'AbortError') return '请求未完成。可以重新连接查询原请求状态。'
  return '网络连接未完成，请检查连接后重试。'
}

export function timeLabel(value: number): string {
  const safe = Math.max(0, Number.isFinite(value) ? value : 0)
  const deciseconds = Math.round(safe * 10)
  const minutes = Math.floor(deciseconds / 600)
  const seconds = Math.floor(deciseconds / 10) % 60
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${deciseconds % 10}`
}

export const eventNames: Record<string, string> = {
  enter: '进入区域', exit: '离开区域', dwell: '出现较久', initial_presence: '已在区域内', observation_gap: '暂时没识别到',
}
