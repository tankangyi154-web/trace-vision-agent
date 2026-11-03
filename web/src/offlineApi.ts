import prepared from 'virtual:prepared-examples'

export function offlineApi<T>(path: string, init: RequestInit): Promise<T> {
  if (init.method && init.method !== 'GET') return Promise.reject(new Error('离线案例版只提供已保存的结果。'))
  if (path === '/api/health') return Promise.resolve({ status: 'ok', live_agent: false, mode: 'offline-examples', reason: null,
    model: '', version: 'offline-v1', limits: {session_questions: 0, daily_questions: 0},
    capabilities: {local_uploads: false, image_analysis: false, video_analysis: false, model_verified: false, missing: []} } as T)
  if (path === '/api/scenes') return Promise.resolve({scenes: []} as T)
  if (path === '/api/presets') return Promise.resolve({presets: prepared.catalog} as T)
  const id = path.match(/^\/api\/presets\/(daylight|lowlight|occlusion)$/)?.[1]
  if (id && prepared.examples[id]) return Promise.resolve(structuredClone(prepared.examples[id]) as T)
  return Promise.reject(new Error('请从首页选择一个离线案例。'))
}
