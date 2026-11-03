export function analysisHint(hasFile: boolean, count: number, pending: boolean): string {
  if (!hasFile) return '先上传一张图片或一段短视频。'
  if (pending) return '输入的物体请先回车或点击添加。'
  if (!count) return '添加1—3种想找的物体，再开始分析。'
  return ''
}

export function analysisProgress(job: { phase?: string; processed: number; total: number; elapsed_seconds?: number; eta_seconds?: { low: number; high: number } | null }): string {
  const seconds = job.elapsed_seconds || 0
  const elapsed = seconds >= 60 ? `${Math.floor(seconds / 60)}分${seconds % 60}秒` : `${seconds}秒`
  if (job.phase === 'rendering' || job.phase === 'complete') return `画面识别已完成，正在整理标注视频与截图 · 已用${elapsed}`
  if (job.total) {
    const estimate = job.eta_seconds
    const wait = (value: number) => value >= 60 ? `${Math.ceil(value / 60)}分钟` : `${Math.ceil(value)}秒`
    return `已识别 ${job.processed} / ${job.total} 个画面 · 已用${elapsed}` + (estimate ? ` · 预计还需约${wait(estimate.low)}—${wait(estimate.high)}` : '')
  }
  return job.phase === 'queued' ? '正在等待前一份素材处理完成。' : `正在准备素材 · 已用${elapsed}`
}

export function shouldFollowMessages(view: { scrollHeight: number; scrollTop: number; clientHeight: number }): boolean {
  return view.scrollHeight - view.scrollTop - view.clientHeight <= 64
}

export function isNewReply(current: { id?: string; answer?: string | null }, previous: { id?: string; answer?: string | null }): boolean {
  return !!current.id && current.id === previous.id && !!current.answer && current.answer !== previous.answer
}
