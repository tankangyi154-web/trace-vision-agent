export type MediaScope = { start_seconds: number; end_seconds: number }
export function validMediaScope(value: unknown, duration = 120): value is MediaScope {
  if (!value || typeof value !== 'object') return false
  const row = value as Record<string, unknown>
  return typeof row.start_seconds === 'number' && Number.isFinite(row.start_seconds)
    && typeof row.end_seconds === 'number' && Number.isFinite(row.end_seconds)
    && row.start_seconds >= 0 && row.end_seconds > row.start_seconds && row.end_seconds <= duration + .05
}
