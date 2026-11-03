export type ObjectChoice = { id: number; name: string; label: string; aliases?: string[] }
const normalize = (text: string) => text.normalize('NFKC').trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')

export function resolveObjectNames(text: string, choices: ObjectChoice[], selected: number[]) {
  const names = text.split(/[,，、;；\r\n]+/).map(s => s.trim()).filter(Boolean)
  if (!names.length) return { ids: [...selected], error: '请先输入物体名称。', notice: '' }
  const found = names.map(name => choices.find(c => [c.name, c.label, ...(c.aliases || [])].some(value => normalize(value) === normalize(name))))
  const unsupported = names.filter((_, index) => !found[index])
  if (unsupported.length) return { ids: [...selected], error: `当前模型暂不支持“${unsupported.join('、')}”，请更换名称或查看可识别物体。`, notice: '' }
  const ids = [...new Set([...selected, ...found.map(c => c!.id)])]
  if (ids.length > 3) return { ids: [...selected], error: '首次最多添加3种物体，请先移除一种；分析后还可以继续提问补找。', notice: '' }
  return { ids, error: '', notice: `已加入识别范围：${[...new Set(found.map(c => c!.name))].join('、')}。` }
}
