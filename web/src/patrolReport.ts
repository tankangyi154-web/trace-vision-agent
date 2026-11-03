import { statisticsScope } from './statisticsFeedback'
import { reviewLabel } from './patrolReviews'
import { timeLabel } from './api'
import type { PatrolItem } from './patrol'
import type { PatrolReview } from './patrolReviews'
import type { Analysis, Scene } from './types'

const escape = (value: unknown) => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
export function publicEvidenceUrl(value: string, sceneId: string, origin: string): string | null {
  try { const base = new URL(origin); if (!['http:', 'https:'].includes(base.protocol) || base.origin !== origin) return null } catch { return null }
  if (!/^[a-z0-9-]+$/.test(sceneId)) return null
  const prefix = `/media/${sceneId}/evidence/`
  if (!value.startsWith(prefix) || !/^frame-\d+\.jpg$/.test(value.slice(prefix.length))) return null
  return origin + value
}
export function patrolPayload(scene: Scene, analysis: Analysis, items: PatrolItem[], records: Record<string, PatrolReview>) {
  return { report_kind: 'patrol-human-review-v1', generated_at: new Date().toISOString(), scene: { id: scene.id, title: scene.title, source: scene.source },
    scope: { id: analysis.review_scope_id, zone_id: analysis.zone_id, dwell_seconds: analysis.dwell_seconds, rules_version: analysis.rules_version },
    items: items.map(item => ({ ...item, manual_review: records[item.id]?.scope === analysis.review_scope_id ? records[item.id] : null })) }
}
export function patrolDocument(scene: Scene, analysis: Analysis, items: PatrolItem[], records: Record<string, PatrolReview>, pictures: Record<string, string>, origin: string): string {
  const payload = patrolPayload(scene, analysis, items, records)
  const checked = payload.items.filter(item => item.manual_review?.status === 'checked').length
  const uncertain = payload.items.filter(item => item.manual_review?.status === 'uncertain').length
  const rows = payload.items.map(item => {
    const review = item.manual_review
    const images = item.evidence.map(e => {
      const data = pictures[e.id]
      const url = publicEvidenceUrl(e.image_url, scene.id, origin)
      const image = data && /^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(data)
        ? `<img src="${data}" alt="${escape(item.name)}，${timeLabel(e.t)}的实际画面">`
        : `<p>本图未能嵌入。${url ? `<a href="${escape(url)}">在本地服务中查看截图</a>` : '请在项目中按时间回看。'}</p>`
      return `<figure>${image}<figcaption>${timeLabel(e.t)} · ${escape(e.id)}</figcaption></figure>`
    }).join('')
    return `<section><h2>${escape(item.title)}</h2><p>${escape(item.description)}</p><p>回看片段：${timeLabel(item.start)}—${timeLabel(item.end)}。截图时间与片段边界可能略有差异。</p><ul>${item.facts.map(f => `<li>${escape(f)}</li>`).join('')}</ul><p><strong>人工核对：${reviewLabel(review?.status)}</strong>${review ? ` · ${escape(new Date(review.updatedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }))}` : ''}</p><p class="note">${escape(review?.note || '尚无人工补充说明。')}</p><div class="pictures">${images}</div></section>`
  }).join('')
  const sourceUrl = /^https?:\/\//.test(scene.source.url) ? scene.source.url : ''
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Trace 巡查核对单</title><style>body{max-width:1000px;margin:32px auto;padding:0 24px;font:16px/1.8 system-ui;color:#142a43}h1{font-size:28px}h2{font-size:20px}section{border-top:1px solid #dce3ed;padding:24px 0}.pictures{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:240px}img{width:100%;height:auto}figcaption,footer{font-size:13px;color:#536780;overflow-wrap:anywhere}.note{white-space:pre-wrap}code{overflow-wrap:anywhere}@media print{section{break-inside:avoid}}</style></head><body><h1>视迹 Trace · 巡查核对单</h1><p>${escape(scene.title)} · ${escape(statisticsScope(scene, analysis))}</p><p>共${items.length}条记录；已核对${checked}条；仍无法确认${uncertain}条；待核对${items.length - checked - uncertain}条。</p><p>程序整理的视频事实与人工核对意见分别记录，不作为真实身份、停止不动或违规行为的确认。</p>${rows || '<p>当前设置下没有相关片段记录。</p>'}<footer><p>视频来源：${sourceUrl ? `<a href="${escape(sourceUrl)}">${escape(scene.source.title)}</a>` : escape(scene.source.title)}；作者：${escape(scene.source.author)}；许可：${escape(scene.source.license)}。</p><p>数据与规则版本：<code>${escape(analysis.review_scope_id || '未提供')}</code>；${escape(analysis.rules_version)}。</p><p>导出时间：${escape(new Date(payload.generated_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }))}。核对记录来源于当前浏览器，导出后可独立保存。</p></footer></body></html>`
}
