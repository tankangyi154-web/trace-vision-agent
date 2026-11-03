import { shortZone } from './plainLanguage'
import type { Analysis, Scene } from './types'

export function validStatisticsSeconds(value: unknown): boolean {
  const seconds = typeof value === 'number' || typeof value === 'string' ? Number(value) : NaN
  return Number.isFinite(seconds) && seconds >= .5 && seconds <= 60
}

export function statisticsScope(scene: Scene, analysis: Analysis): string {
  const zone = scene.zones.find(item => item.id === analysis.zone_id)
  return `${shortZone(zone?.name || `区域 ${analysis.zone_id}`)} · 连续出现至少${analysis.dwell_seconds}秒`
}

export function statisticsFeedback(scene: Scene, previous: Analysis | null, next: Analysis): string {
  const count = next.summary.dwell_alerts
  const sameZone = previous?.scene_id === next.scene_id && previous?.zone_id === next.zone_id
  const before = previous?.summary.dwell_alerts
  const comparison = sameZone
    ? before === count ? `符合条件的记录仍为${count}段。` : `符合条件的记录由${before}段变为${count}段。`
    : `找到${count}段符合条件的记录。`
  // An accumulated total or an interval spanning a gap is not a continuous duration.
  const longest = Number(Math.max(0, ...next.dwell.flatMap(item => item.intervals.map(interval => interval.end - interval.start))).toFixed(3))
  let reason = ''
  if (longest > 0 && count === 0) reason = `最长连续识别${longest}秒，未达到${next.dwell_seconds}秒。`
  else if (longest > 0 && sameZone && before === count && previous.dwell_seconds !== next.dwell_seconds) {
    reason = `最长连续识别${longest}秒，调整后仍符合要求。`
  }
  return `已按“${statisticsScope(scene, next)}”重新统计。${comparison}${reason}`
}
