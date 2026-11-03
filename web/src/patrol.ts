import { targetName, shortZone } from './plainLanguage'
import { timeLabel } from './api'
import type { Analysis, Dwell, Evidence, Scene, Track, VideoEvent } from './types'

export interface PatrolItem {
  id: string; trackId: string; name: string; kind: 'gap' | 'duration' | 'movement'
  title: string; description: string; start: number; end: number
  observed: number; longest: number; gaps: VideoEvent[]; events: VideoEvent[]
  evidence: Evidence[]; facts: string[]; canInvestigate: boolean
}
const close = (a: number, b: number) => Math.abs(a - b) < .001
const seconds = (n: number) => Number(n.toFixed(3))

/** One appearance episode may contain an unresolved gap, but the gap never becomes observed duration. */
export function buildPatrolItems(scene: Scene, analysis: Analysis): PatrolItem[] {
  const zone = shortZone(scene.zones.find(z => z.id === analysis.zone_id)?.name || `区域 ${analysis.zone_id}`)
  const tolerance = Math.max(.5, 2 / scene.fps)
  const items: PatrolItem[] = []
  for (const track of analysis.dwell) {
    const events = analysis.events.filter(e => e.track_id === track.track_id)
    const gaps = events.filter(e => e.type === 'observation_gap')
    const episodes: { intervals: Dwell['intervals']; gaps: VideoEvent[] }[] = []
    for (const interval of [...track.intervals].sort((a, b) => a.start - b.start)) {
      const previous = episodes.at(-1)
      const last = previous?.intervals.at(-1)
      if (last && gaps.some(g => close(g.start, last.end) && close(g.end, interval.start))) previous!.intervals.push(interval)
      else episodes.push({ intervals: [interval], gaps: [] })
    }
    for (const episode of episodes) {
      episode.gaps = gaps.filter(g => episode.intervals.some(i => close(g.start, i.end) || close(g.end, i.start)))
      const first = episode.intervals[0]!, last = episode.intervals.at(-1)!
      const entry = events.find(e => e.type === 'enter' && close(e.start, first.start))
      const exit = !last.censored ? events.find(e => e.type === 'exit' && e.start >= last.end && e.start - last.end <= tolerance + .001) : undefined
      const longest = seconds(Math.max(...episode.intervals.map(i => i.end - i.start)))
      const observed = seconds(episode.intervals.reduce((sum, i) => sum + i.end - i.start, 0))
      const qualifies = longest + 1e-9 >= analysis.dwell_seconds
      if (!qualifies && !episode.gaps.length && !entry && !exit) continue
      const start = Math.max(0, Math.min(first.start, ...episode.gaps.map(g => g.start)))
      const end = Math.min(scene.duration, Math.max(last.end, exit?.start || last.end, ...episode.gaps.map(g => g.end)))
      const name = targetName(track.track_id, track.label)
      const kind = episode.gaps.length ? 'gap' : qualifies ? 'duration' : 'movement'
      const gapSeconds = seconds(episode.gaps.reduce((sum, g) => sum + g.duration, 0))
      const description = kind === 'gap'
        ? `有${gapSeconds}秒未能识别，最长连续识别${longest}秒。${qualifies ? '已识别的片段达到当前时长设置，但中断期间是否在场仍无法确认。' : `现有画面无法确认连续达到${analysis.dwell_seconds}秒。`}`
        : qualifies ? `在${zone}，连续识别${longest}秒，达到设置的${analysis.dwell_seconds}秒。`
          : entry ? `观察到它进入${zone}${exit ? '，随后离开。' : '，这段记录尚未确认离开时间。'}` : `观察到它离开${zone}，进入时间尚未确认。`
      const candidates = analysis.evidence.filter(e => e.track_id === track.track_id && e.t >= start - tolerance && e.t <= end + tolerance)
      const anchors = episode.gaps.length ? [episode.gaps[0]!.start, episode.gaps.at(-1)!.end, (last.start + last.end) / 2] : [first.start, (first.start + last.end) / 2, exit?.start || last.end]
      const pictures = [...new Map(anchors.flatMap(t => {
        const candidate = [...candidates].sort((a, b) => Math.abs(a.t - t) - Math.abs(b.t - t))[0]
        return candidate ? [[candidate.id, candidate] as const] : []
      })).values()].sort((a, b) => a.t - b.t)
      items.push({ id: `${track.track_id}:${first.start.toFixed(3)}:${last.end.toFixed(3)}`, trackId: track.track_id, name, kind,
        title: kind === 'gap' ? `${name}的连续出现还需要核对` : qualifies ? `${name}达到设定出现时长` : `${name}有一段进出记录`,
        description, start: end > start ? start : Math.max(0, start - .5), end: end > start ? end : Math.min(scene.duration, end + .5), longest, observed, gaps: episode.gaps,
        events: events.filter(e => e.start >= start && e.start <= end), evidence: pictures,
        facts: [`累计能确认出现${observed}秒；最长连续识别${longest}秒`, entry ? `观察到进入：${timeLabel(entry.start)}` : '进入时间尚未确认', exit ? `观察到离开：${timeLabel(exit.start)}` : '离开时间尚未确认'],
        canInvestigate: scene.id === 'harbor' && analysis.zone_id === 'A' && track.track_id === 'T001' && episode.gaps.some(g => close(g.start, 12.3) && close(g.end, 13.1)),
      })
    }
  }
  const priority = { gap: 0, duration: 1, movement: 2 }
  return items.sort((a, b) => priority[a.kind] - priority[b.kind] || a.start - b.start || a.trackId.localeCompare(b.trackId))
}

export function clipRange(start: number, end: number, duration: number): { start: number; end: number } | null {
  if (![start, end, duration].every(Number.isFinite) || duration <= 0) return null
  const bounded = { start: Math.max(0, Math.min(duration, start)), end: Math.max(0, Math.min(duration, end)) }
  return bounded.end > bounded.start ? bounded : null
}

export function sampleAtTime(track: Track | undefined, time: number, fps: number) {
  if (!track || !Number.isFinite(time) || !Number.isFinite(fps) || fps <= 0) return null
  const frame = Math.floor((time + .00001) * fps)
  return track.samples.find(sample => sample.frame === frame) || null
}

export function observedTrajectories(track: Track | undefined, fps: number, range?: { start: number; end: number } | null): string[] {
  if (!track || !Number.isFinite(fps) || fps <= 0) return []
  const segments: string[][] = [], tolerance = Math.max(.5, 2 / fps)
  let previous = -Infinity
  for (const sample of [...track.samples].sort((a, b) => a.t - b.t)) {
    if (range && (sample.t < range.start || sample.t > range.end)) continue
    if (sample.t - previous > tolerance + .00001) segments.push([])
    segments.at(-1)!.push(`${(sample.bbox[0] + sample.bbox[2]) * 500},${(sample.bbox[1] + sample.bbox[3]) * 500}`)
    previous = sample.t
  }
  return segments.filter(segment => segment.length > 1).map(segment => segment.join(' '))
}
