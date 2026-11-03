/** Keep small workspace references in storage; pending files stay in IndexedDB. */
import { validMediaScope, type MediaScope } from './mediaScope'
export const MEDIA_CACHE = 'trace-media-workspace-v2'
const LEGACY_CACHE = 'trace-media-job-v1'
const DRAFT_DB = 'trace-media-drafts-v1'
const RECORDS_CACHE = 'trace-media-records-v1'
export type MediaReference = { id: string; owner: string }
export const DRAFT_TTL = 30 * 60 * 1000
export type MediaCache = {
  segment?: MediaScope
  job: { id: string; owner: string } | null
  classIds: number[]
  draftId: string | null
  time: number
  target: string | null
  panel: 'media' | 'chat'
}
const uuid = /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i
export function emptyMediaCache(): MediaCache { return { job: null, classIds: [], draftId: null, time: 0, target: null, panel: 'media' } }
export function parseMediaCache(raw: string | null): MediaCache | null {
  try {
    const data = JSON.parse(raw || 'null')
    if (!data || data.version !== 2) return null
    const job = data.job && uuid.test(data.job.id) && typeof data.job.owner === 'string' && /^[\w-]{32,64}$/.test(data.job.owner) ? { id: data.job.id, owner: data.job.owner } : null
    const classIds = Array.isArray(data.classIds) ? [...new Set<number>(data.classIds.filter((id: unknown) => Number.isInteger(id) && Number(id) >= 0 && Number(id) < 80))].slice(0, 3) : []
    return { job, classIds, ...(validMediaScope(data.segment) ? { segment: data.segment } : {}), draftId: typeof data.draftId === 'string' && uuid.test(data.draftId) ? data.draftId : null,
      time: typeof data.time === 'number' && Number.isFinite(data.time) && data.time >= 0 ? data.time : 0,
      target: typeof data.target === 'string' && /^\d{1,8}$/.test(data.target) ? data.target : null,
      panel: data.panel === 'chat' ? 'chat' : 'media' }
  } catch { return null }
}
function stores(): Storage[] {
  const result: Storage[] = []
  try { result.push(sessionStorage) } catch { /* Some browsers disable storage. */ }
  try { result.push(localStorage) } catch { /* Tab storage still permits refresh. */ }
  return result
}
export function readMediaCache(): MediaCache {
  for (const storage of stores()) {
    try {
      const cache = parseMediaCache(storage.getItem(MEDIA_CACHE))
      if (cache) return cache
      const legacy = JSON.parse(storage.getItem(LEGACY_CACHE) || 'null')
      if (legacy?.id && legacy?.owner) {
        const migrated = parseMediaCache(JSON.stringify({ version: 2, job: legacy }))
        if (migrated?.job) return migrated
      }
    } catch { /* Try the other storage instead of losing a valid workspace. */ }
  }
  return emptyMediaCache()
}
export function writeMediaCache(cache: MediaCache): boolean {
  let saved = false
  for (const storage of stores()) {
    try { storage.setItem(MEDIA_CACHE, JSON.stringify({ version: 2, ...cache })); storage.removeItem(LEGACY_CACHE); saved = true } catch { /* Keep the other copy. */ }
  }
  return saved
}
export function readMediaRecords(): MediaReference[] {
  try {
    const rows = JSON.parse(localStorage.getItem(RECORDS_CACHE) || '[]')
    return Array.isArray(rows) ? rows.filter(row => row && uuid.test(row.id) && typeof row.owner === 'string' && /^[\w-]{32,64}$/.test(row.owner)) : []
  } catch { return [] }
}
export function rememberMediaRecord(record: MediaReference) {
  try { localStorage.setItem(RECORDS_CACHE, JSON.stringify([record, ...readMediaRecords().filter(row => row.id !== record.id)])) } catch { /* Server inventory remains available for this owner. */ }
}
export function forgetMediaRecord(id: string) {
  try { localStorage.setItem(RECORDS_CACHE, JSON.stringify(readMediaRecords().filter(row => row.id !== id))) } catch { /* Deleted records are also removed by the server. */ }
}
export function isMissingMedia(error: unknown): boolean {
  // A network failure, 5xx response or gateway 404 is not proof of deletion.
  return !!error && typeof error === 'object' && 'status' in error && error.status === 404 && 'code' in error && error.code === 'not_found'
}

async function draftDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DRAFT_DB, 1)
    request.onupgradeneeded = () => { request.result.createObjectStore('files', { keyPath: 'id' }) }
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('File storage is blocked'))
    request.onsuccess = () => resolve(request.result)
  })
}
async function draftOperation<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore, done: (value: T) => void) => void): Promise<T> {
  const db = await draftDB()
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = db.transaction('files', mode)
      let value: T
      transaction.oncomplete = () => resolve(value)
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error || new Error('File storage interrupted'))
      run(transaction.objectStore('files'), result => { value = result })
    })
  } finally { db.close() }
}
export async function saveMediaDraft(id: string, file: File): Promise<void> {
  if (!uuid.test(id)) throw new Error('Invalid draft id')
  await draftOperation<void>('readwrite', store => {
    store.put({ id, file, expiresAt: Date.now() + DRAFT_TTL })
    const cursor = store.openCursor()
    cursor.onsuccess = () => { const item = cursor.result; if (!item) return; if (item.value.expiresAt <= Date.now()) item.delete(); item.continue() }
  })
}
export async function readMediaDraft(id: string): Promise<File | null> {
  if (!uuid.test(id)) return null
  return draftOperation<File | null>('readwrite', (store, done) => {
    const request = store.get(id)
    request.onsuccess = () => {
      const record = request.result
      if (!record || record.expiresAt <= Date.now()) { if (record) store.delete(id); done(null); return }
      done(record.file instanceof File ? record.file : null)
    }
  })
}
export async function deleteMediaDraft(id: string | null): Promise<void> {
  if (id && uuid.test(id)) await draftOperation<void>('readwrite', store => { store.delete(id) })
}
