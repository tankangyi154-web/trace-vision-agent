export type ManualStatus = 'checked' | 'uncertain'
export interface PatrolReview { scope: string; item: string; status: ManualStatus; note: string; updatedAt: string }
export type ReviewStorage = Pick<Storage, 'getItem' | 'setItem'> | null
const KEY = 'trace-patrol-reviews-v1'
export const validScope = (scope: unknown): scope is string => typeof scope === 'string' && /^[a-f0-9]{64}$/.test(scope)
export const reviewLabel = (status?: ManualStatus) => status === 'checked' ? '已核对' : status === 'uncertain' ? '仍无法确认' : '待核对'

function validRecord(value: unknown): value is PatrolReview {
  if (!value || typeof value !== 'object') return false
  const r = value as PatrolReview
  return validScope(r.scope) && typeof r.item === 'string' && r.item.length > 0 && r.item.length < 200
    && ['checked', 'uncertain'].includes(r.status) && typeof r.note === 'string' && r.note.length <= 1200
    && typeof r.updatedAt === 'string' && Number.isFinite(Date.parse(r.updatedAt))
}
function readAll(storage: ReviewStorage): PatrolReview[] {
  if (!storage) return []
  const raw = storage.getItem(KEY)
  if (!raw || raw.length > 2_000_000) return []
  const data = JSON.parse(raw)
  return Array.isArray(data) ? data.filter(validRecord).slice(-400) : []
}
export function readPatrolReviews(storage: ReviewStorage, scope: string): { records: Record<string, PatrolReview>; available: boolean } {
  try { return { records: Object.fromEntries(readAll(storage).filter(r => r.scope === scope).map(r => [r.item, r])), available: !!storage } }
  catch { return { records: {}, available: false } }
}
export function savePatrolReview(storage: ReviewStorage, record: PatrolReview): boolean {
  if (!validRecord(record)) throw new Error('核对记录格式无效，请检查说明与结果。')
  try {
    if (!storage) return false
    let existing: PatrolReview[]
    try { existing = readAll(storage) } catch { existing = [] }
    const next = [...existing.filter(r => r.scope !== record.scope || r.item !== record.item), record].slice(-400)
    storage.setItem(KEY, JSON.stringify(next))
    return true
  } catch { return false }
}
