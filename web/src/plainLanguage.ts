import type { Analysis, ChatContext, ChatResult, Scene, VideoEvent } from './types'

const names: Record<string, string> = { boat: '船', car: '汽车', bus: '公交车', truck: '卡车', motorcycle: '摩托车', bicycle: '自行车', person: '人', dog: '狗', cat: '猫', traffic_light: '交通灯' }
export function objectName(label: string): string { return names[label.replace(/ /g, '_')] || (/^[\u4e00-\u9fff]+$/.test(label) ? label : '物体') }
export function targetName(id: string, label = ''): string {
  const number = /^(?:T)?0*(\d+)$/i.exec(id)?.[1]
  return number ? `${number}号${objectName(label)}` : objectName(label)
}
export function shortZone(name: string): string { return name.replace(/^区域\s*[A-Za-z0-9]+\s*[·:：-]\s*/, '') }
export function eventDescription(event: VideoEvent, threshold: number): string {
  return ({
    enter: '画面中看到它进入了这个区域。',
    exit: '画面中看到它离开了这个区域。',
    dwell: `在这个区域内连续识别到它，时间达到${threshold}秒。`,
    initial_presence: '第一次看到或重新识别到它时，它已经在区域内，进入时间不确定。',
    observation_gap: '有一段时间没有识别到它，原因还不能确定。',
  })[event.type]
}
export function chatStage(stage: string): string {
  if (/补充识别|查找.*物体/.test(stage)) return '正在查找你提到的物体…'
  if (/模型|组织|生成回答/.test(stage)) return '正在整理回答…'
  return '正在核对画面和时间…'
}

function readableText(text: string, result: ChatResult, scene?: Scene | null): string {
  let value = text
  for (const citation of result.citations || []) value = value.split(citation.evidence_id).join('')
  value = value.replace(/证据[：:]\s*[，、,.。\s]*$/u, '')
  if (scene) value = value.split(`（${scene.id}）`).join('').split(`(${scene.id})`).join('')
  value = value.replace(/\bcensored\b/gi, '起止不完整')
    .replace(/可观测驻留时长/g, '画面中能确认的出现时间')
    .replace(/累计可观测驻留/g, '累计能确认的出现时间')
    .replace(/观测中断/g, '暂时没识别到')
  for (const [label, name] of Object.entries(names)) value = value.replace(new RegExp(`\\b${label}\\b`, 'g'), name)
  return value.trim()
}

/** A short display summary uses the same visible, scoped calculation and a cited target.
 *  It never rewrites refusals, review verdicts, failed requests or continuous-duration questions.
 *  The complete original response remains available in the analysis details. */
export function plainAnswer(result: ChatResult | undefined, question: string, context: ChatContext, scene?: Scene | null, analysis?: Analysis | null): string {
  if (!result?.answer) return ''
  const fallback = readableText(result.answer, result, scene)
  if (result.status !== 'complete' || result.error || result.insufficient_evidence || context.investigation_id
    || result.verification || !scene || !analysis || scene.id !== context.scene_id || analysis.scene_id !== context.scene_id
    || analysis.zone_id !== context.zone_id || analysis.dwell_seconds !== context.dwell_seconds) return fallback
  const calls = result.tool_calls || []
  const cited = (id: string) => (result.citations || []).some(citation => citation.track_id === id && analysis.evidence.some(e => e.id === citation.evidence_id))
  const globalCall = (name: string) => calls.some(call => call.name === name && !call.arguments?.track_id)
  const simpleQuestion = question.trim().replace(/[？?。！!\s]/g, '')
  const asksLongest = /^(谁|哪个目标|哪个物体|哪个)(在区域里|在区域内|在所选区域里)?(出现|停留|驻留)(得)?(最久|最长)$/.test(simpleQuestion)
  if (asksLongest && globalCall('calculate_dwell')) {
    const ranked = [...analysis.dwell].sort((a, b) => b.observed_seconds - a.observed_seconds)
    const first = ranked[0]
    if (!first || !cited(first.track_id)) return fallback
    const tied = ranked.some((item, index) => index > 0 && item.observed_seconds === first.observed_seconds)
    const name = targetName(first.track_id, first.label)
    const duration = Number(first.observed_seconds.toFixed(3))
    const limit = first.intervals.length > 1
      ? '中间有一段没识别到，无法确认它一直在那里。'
      : '这是视频里能确认的时间，不代表它实际停留的全部时间。'
    return `${name}${tied ? '是并列出现最久的标记之一' : '在所选区域里出现最久'}，累计能确认${duration}秒。${limit}`
  }
  const searchedEntries = calls.some(call => call.name === 'search_events' && !call.arguments?.track_id && ['all', 'enter', undefined].includes(call.arguments?.event_type as string | undefined))
  const asksEntries = /^(哪些物体|哪些目标|谁)进入了?(这个|所选)?区域$/.test(simpleQuestion)
    || /^(进入了几次|进入了多少次|进入区域有几次|进入区域多少次)$/.test(simpleQuestion)
  if (asksEntries && searchedEntries) {
    const entries = analysis.events.filter(event => event.type === 'enter')
    const visible = [...new Map(entries.filter(event => cited(event.track_id)).map(event => [event.track_id, event])).values()]
    if (!entries.length || !visible.length) return fallback
    const list = visible.slice(0, 3).map(event => targetName(event.track_id, event.label)).join('、')
    const more = visible.length < new Set(entries.map(event => event.track_id)).size || visible.length > 3
    if (/(几次|多少次)/.test(question)) return `画面中记录到${entries.length}次进入所选区域。点击下方的时间点，可以回看对应画面。`
    return `看到${list}${more ? '等标记' : ''}进入了所选区域。点击下方的时间点，可以回看对应画面。`
  }
  return fallback
}
