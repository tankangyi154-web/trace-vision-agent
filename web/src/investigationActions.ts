export interface InvestigationAgentHandle {
  canAsk: boolean
  sendQuestion(question: string): Promise<void>
}

export async function startAgentInvestigation(agent: InvestigationAgentHandle | null, question: string, scrollToExecution: () => void): Promise<boolean> {
  if (!agent?.canAsk || !question.trim()) return false
  scrollToExecution()
  await agent.sendQuestion(question)
  return true
}

export function reviewRecordLabel(createdAt: string, previous: boolean): string {
  const date = new Date(createdAt)
  const time = Number.isNaN(date.getTime()) ? '创建时间未返回' : new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date)
  return `${previous ? '上次实际复核记录' : '本次使用的实际复核记录'} · ${time}`
}
